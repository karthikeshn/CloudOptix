"""
EC2 Graviton Migration Pricing Plugin

Responsibility:
    FINANCIAL MATH ONLY.

This module:
    1. Receives discovered EC2 resources.
    2. Calculates a fallback current EC2 cost using estimated AWS rates.
    3. Queries the centralized CUR integration for historical cost.
    4. Calculates projected Graviton cost.
    5. Calculates monthly savings.
    6. Returns the original dictionaries enriched with:
           currentDailyCost
           currentMonthlyCost
           estimatedMonthlySavings

Public API:
    calculate_savings(discovered_resources, account_id=None)
"""

import os
import sys


# ---------------------------------------------------------------------------
# Import centralized CUR integration
# ---------------------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIRECTORY = os.path.dirname(CURRENT_DIR)

if BACKEND_DIRECTORY not in sys.path:
    sys.path.append(BACKEND_DIRECTORY)

from utils import cur_integration


# ---------------------------------------------------------------------------
# Estimated AWS hourly rates
#
# These are intentionally used as FALLBACK estimates only.
#
# The authoritative historical cost is obtained from CUR whenever
# cur_integration.get_historical_cost() can return it.
#
# Values represent approximate On-Demand Linux hourly pricing and should
# be maintained periodically as AWS pricing changes.
# ---------------------------------------------------------------------------

ESTIMATED_HOURLY_RATES = {

    # -----------------------------------------------------------------------
    # M5 -> M6G
    # -----------------------------------------------------------------------

    "m5.large": 0.096,
    "m5.xlarge": 0.192,
    "m5.2xlarge": 0.384,
    "m5.4xlarge": 0.768,
    "m5.8xlarge": 1.536,
    "m5.12xlarge": 2.304,
    "m5.16xlarge": 3.072,
    "m5.24xlarge": 4.608,

    "m6g.large": 0.077,
    "m6g.xlarge": 0.154,
    "m6g.2xlarge": 0.308,
    "m6g.4xlarge": 0.616,
    "m6g.8xlarge": 1.232,
    "m6g.12xlarge": 1.848,
    "m6g.16xlarge": 2.464,

    # -----------------------------------------------------------------------
    # C5 -> C6G
    # -----------------------------------------------------------------------

    "c5.large": 0.085,
    "c5.xlarge": 0.170,
    "c5.2xlarge": 0.340,
    "c5.4xlarge": 0.680,
    "c5.9xlarge": 1.530,
    "c5.12xlarge": 1.632,
    "c5.18xlarge": 1.530,
    "c5.24xlarge": 2.040,

    "c6g.large": 0.068,
    "c6g.xlarge": 0.136,
    "c6g.2xlarge": 0.272,
    "c6g.4xlarge": 0.544,
    "c6g.8xlarge": 1.088,
    "c6g.12xlarge": 1.632,
    "c6g.16xlarge": 2.176,

    # -----------------------------------------------------------------------
    # R5 -> R6G
    # -----------------------------------------------------------------------

    "r5.large": 0.126,
    "r5.xlarge": 0.252,
    "r5.2xlarge": 0.504,
    "r5.4xlarge": 1.008,
    "r5.8xlarge": 2.016,
    "r5.12xlarge": 3.024,
    "r5.16xlarge": 4.032,
    "r5.24xlarge": 6.048,

    "r6g.large": 0.1008,
    "r6g.xlarge": 0.2016,
    "r6g.2xlarge": 0.4032,
    "r6g.4xlarge": 0.8064,
    "r6g.8xlarge": 1.6128,
    "r6g.12xlarge": 2.4192,
    "r6g.16xlarge": 3.2256,

    # -----------------------------------------------------------------------
    # T3 -> T4G
    # -----------------------------------------------------------------------

    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t3.large": 0.0832,
    "t3.xlarge": 0.1664,
    "t3.2xlarge": 0.3328,

    "t4g.micro": 0.0084,
    "t4g.small": 0.0168,
    "t4g.medium": 0.0336,
    "t4g.large": 0.0672,
    "t4g.xlarge": 0.1344,
    "t4g.2xlarge": 0.2688,
}


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HOURS_PER_DAY = 24
DAYS_PER_MONTH = 30
HOURS_PER_MONTH = HOURS_PER_DAY * DAYS_PER_MONTH


# ---------------------------------------------------------------------------
# Financial helpers
# ---------------------------------------------------------------------------

def get_estimated_hourly_rate(instance_type):
    """
    Return the configured estimated hourly rate.

    If the exact instance type is unavailable, return 0.0 rather than
    inventing a rate.
    """
    return float(
        ESTIMATED_HOURLY_RATES.get(
            instance_type,
            0.0
        )
    )


def calculate_estimated_monthly_cost(instance_type):
    """
    Calculate estimated monthly cost from the configured AWS hourly rate.
    """
    hourly_rate = get_estimated_hourly_rate(
        instance_type
    )

    return hourly_rate * HOURS_PER_MONTH


def calculate_fallback_current_cost(instance_type):
    """
    Calculate fallback current monthly cost.

    This value is used only when CUR does not provide historical cost.
    """
    return calculate_estimated_monthly_cost(
        instance_type
    )


def calculate_projected_cost(target_instance_type):
    """
    Calculate projected monthly cost after migrating to Graviton.

    This uses the estimated AWS rate for the target Graviton instance.
    """
    return calculate_estimated_monthly_cost(
        target_instance_type
    )


def format_currency(value):
    """
    Convert a numeric financial value into the required dashboard format.
    """
    return f"${max(float(value), 0.0):.2f}"


# ---------------------------------------------------------------------------
# Required public function
# ---------------------------------------------------------------------------

def calculate_savings(
    discovered_resources,
    account_id=None
):
    """
    Calculate current cost, projected Graviton cost, and savings.

    Parameters
    ----------
    discovered_resources : list[dict]
        Resources discovered by the Analysis Script.

    account_id : str | None
        AWS account ID used for the CUR lookup.

    Returns
    -------
    list[dict]
        The same dictionaries enriched with:
            currentDailyCost
            currentMonthlyCost
            estimatedMonthlySavings
    """

    enriched_resources = []

    for resource in discovered_resources:

        # ---------------------------------------------------------------
        # Resource metadata
        # ---------------------------------------------------------------

        resource_id = resource.get("resourceId")

        current_instance_type = resource.get(
            "currentInstanceType"
        )

        target_instance_type = resource.get(
            "targetInstanceType"
        )

        # ---------------------------------------------------------------
        # STEP 1
        # Calculate fallback current cost.
        #
        # This is used only if CUR does not have usable historical
        # cost information.
        # ---------------------------------------------------------------

        fallback_current_cost = calculate_fallback_current_cost(
            current_instance_type
        )

        # ---------------------------------------------------------------
        # STEP 2
        # Fetch true historical cost from centralized CUR integration.
        # ---------------------------------------------------------------

        current_cost = cur_integration.get_historical_cost(
            resource_id=resource_id,
            account_id=account_id,
            fallback_cost=fallback_current_cost
        )

        # Defensive conversion in case CUR returns Decimal/string/etc.
        try:
            current_cost = float(current_cost)
        except (TypeError, ValueError):
            current_cost = fallback_current_cost

        # Prevent negative historical cost from producing misleading
        # savings values.
        current_cost = max(
            current_cost,
            0.0
        )

        # ---------------------------------------------------------------
        # STEP 3
        # Calculate projected Graviton monthly cost.
        # ---------------------------------------------------------------

        projected_cost = calculate_projected_cost(
            target_instance_type
        )

        # ---------------------------------------------------------------
        # STEP 4
        # Calculate savings.
        #
        # Savings = current historical cost
        #           -
        #           projected Graviton cost
        # ---------------------------------------------------------------

        savings = current_cost - projected_cost

        # Do not report negative "savings".
        savings = max(
            savings,
            0.0
        )

        # ---------------------------------------------------------------
        # STEP 5
        # Calculate daily cost.
        #
        # The pipeline defines the monthly period as 30 days.
        # ---------------------------------------------------------------

        current_daily_cost = (
            current_cost / DAYS_PER_MONTH
        )

        # ---------------------------------------------------------------
        # STEP 6
        # Preserve the exact original dictionary and enrich it.
        # ---------------------------------------------------------------

        enriched_resource = dict(resource)

        enriched_resource["currentDailyCost"] = format_currency(
            current_daily_cost
        )

        enriched_resource["currentMonthlyCost"] = format_currency(
            current_cost
        )

        enriched_resource["estimatedMonthlySavings"] = format_currency(
            savings
        )

        enriched_resources.append(
            enriched_resource
        )

    return enriched_resources