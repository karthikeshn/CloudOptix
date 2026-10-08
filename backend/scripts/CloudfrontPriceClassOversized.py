from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
import pandas as pd
import json


# ============================================================
# 1. AWS CLIENT CONFIGURATION
# ============================================================

AWS_CONFIG = Config(
    retries={
        "mode": "adaptive",
        "max_attempts": 10,
    }
)


# ============================================================
# 2. FINOPS POLICY CONFIGURATION
# ============================================================

POLICY_NAME = "Cloudfront Price Class Oversized"

CATEGORY = "Cloudfront Price Class Oversized"

SERVICE_NAME = "CloudFront"

EFFORT_LEVEL = "Medium"

# CloudFront is a global service.
CLOUDFRONT_REGION = "us-east-1"
GLOBAL_REGION = "global"

# Lookback period for CloudWatch traffic analysis.
LOOKBACK_DAYS = 30

# Minimum monthly traffic required before considering
# PriceClass_All as a potential optimization candidate.
#
# Example:
# 100 GB/month means distributions with less than this
# traffic will not be flagged.
MIN_MONTHLY_TRAFFIC_GB = 0.0

# Approximate premium-region traffic percentage used only
# when producing an optional savings estimate.
#
# IMPORTANT:
# This is NOT an AWS pricing calculation.
# It is a configurable business assumption.
#
# Set to None if you do not want estimated savings.
ASSUMED_PREMIUM_REGION_SHARE = 0.05

# Number of days used to convert daily CloudWatch traffic
# into an approximate monthly traffic value.
DAYS_PER_MONTH = 30


# ============================================================
# 3. STANDARD EXCEL COLUMNS
# ============================================================

STANDARD_COLUMNS = [
    "workItemType",
    "state",
    "id",
    "title",
    "category",
    "owner",
    "assignedTo",
    "status",
    "areaPath",
    "tags",
    "commentCount",
    "accountId",
    "region",
    "resourceNameOrId",
    "resourceId",
    "resourceArn",
    "service",
    "type",
    "policy",
    "effortLevel",
    "message",
    "recommendation",
    "description",
    "currentDailyCost",
    "currentMonthlyCost",
    "estimatedMonthlySavings",
    "approvalComments",
    "reasonForRejection",
    "achievedSavingsMonthly",
    "month",
]


# ============================================================
# 4. AWS CLIENTS
# ============================================================

def create_clients(
    region_name: str,
):
    """
    Create AWS clients required by this policy.

    CloudFront APIs are global, but the CloudFront API endpoint
    is accessed through us-east-1.

    CloudWatch is also queried from us-east-1 for CloudFront
    global metrics.
    """

    cloudfront = boto3.client(
        "cloudfront",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    cloudwatch = boto3.client(
        "cloudwatch",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    return cloudfront, cloudwatch, sts


def get_account_id(sts) -> str:
    """
    Return the AWS account ID.
    """

    return sts.get_caller_identity()["Account"]


# ============================================================
# 5. CLOUDFRONT RESOURCE FETCHER
# ============================================================

def fetch_all_distributions(
    cloudfront,
) -> List[Dict[str, Any]]:
    """
    Fetch all CloudFront distributions using the Boto3 paginator.

    This prevents the scanner from only processing the first page
    of distributions.
    """

    distributions: List[Dict[str, Any]] = []

    paginator = cloudfront.get_paginator(
        "list_distributions"
    )

    for page in paginator.paginate():

        distribution_list = page.get(
            "DistributionList",
            {},
        )

        items = distribution_list.get(
            "Items",
            [],
        )

        distributions.extend(items)

    return distributions


# ============================================================
# 6. CLOUDFRONT DISTRIBUTION DETAILS
# ============================================================

def get_distribution_details(
    cloudfront,
    distribution_id: str,
) -> Dict[str, Any]:
    """
    Fetch complete configuration/details for a CloudFront
    distribution.
    """

    response = cloudfront.get_distribution(
        Id=distribution_id,
    )

    return response.get(
        "Distribution",
        {},
    )


# ============================================================
# 7. CLOUDWATCH METRICS
# ============================================================

def get_bytes_downloaded(
    cloudwatch,
    distribution_id: str,
    lookback_days: int = LOOKBACK_DAYS,
) -> float:
    """
    Fetch CloudFront BytesDownloaded for the specified
    distribution over the configured lookback period.

    CloudFront publishes its metrics under AWS/CloudFront
    with the DistributionId dimension.

    BytesDownloaded uses Sum as the appropriate statistic.
    """

    end_time = datetime.now(
        timezone.utc,
    )

    start_time = end_time - timedelta(
        days=lookback_days,
    )

    total_bytes = 0.0

    try:

        paginator = cloudwatch.get_paginator(
            "get_metric_statistics",
        )

        # CloudWatch get_metric_statistics does not have a
        # paginator in the standard API, so this fallback is
        # intentionally kept simple.
        #
        # One 30-day request with 86400-second periods provides
        # daily data points.

        response = cloudwatch.get_metric_statistics(
            Namespace="AWS/CloudFront",
            MetricName="BytesDownloaded",
            Dimensions=[
                {
                    "Name": "DistributionId",
                    "Value": distribution_id,
                },
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400,
            Statistics=[
                "Sum",
            ],
        )

        datapoints = response.get(
            "Datapoints",
            [],
        )

        for datapoint in datapoints:

            total_bytes += float(
                datapoint.get(
                    "Sum",
                    0.0,
                )
            )

    except ClientError as exc:

        print(
            f"[WARN] CloudWatch metric error for "
            f"{distribution_id}: {exc}"
        )

    return total_bytes


# ============================================================
# 8. TRAFFIC CONVERSION
# ============================================================

def bytes_to_gb(
    bytes_value: float,
) -> float:
    """
    Convert bytes to GB using decimal GB.
    """

    return bytes_value / (
        1024 ** 3
    )


def calculate_monthly_traffic_gb(
    total_bytes: float,
    lookback_days: int,
) -> float:
    """
    Normalize the observed traffic into an approximate
    30-day monthly traffic value.

    Example:

    15 days observed
    -> calculate average daily traffic
    -> multiply by 30
    """

    if total_bytes <= 0:
        return 0.0

    traffic_gb = bytes_to_gb(
        total_bytes,
    )

    if lookback_days <= 0:
        return traffic_gb

    average_daily_gb = (
        traffic_gb / lookback_days
    )

    return (
        average_daily_gb
        * DAYS_PER_MONTH
    )


# ============================================================
# 9. BUSINESS LOGIC
# ============================================================

def is_candidate(
    distribution: Dict[str, Any],
    monthly_traffic_gb: float,
) -> bool:
    """
    Determine whether a CloudFront distribution is a
    Price Class Oversized candidate.

    Current policy:

    1. Distribution must use PriceClass_All.
    2. Distribution must be enabled.
    3. Monthly traffic must exceed configured threshold.
    """

    price_class = distribution.get(
        "PriceClass",
    )

    enabled = distribution.get(
        "Enabled",
        False,
    )

    if price_class != "PriceClass_All":
        return False

    if not enabled:
        return False

    if monthly_traffic_gb < MIN_MONTHLY_TRAFFIC_GB:
        return False

    return True


# ============================================================
# 10. RECOMMENDATION
# ============================================================

def build_recommendation(
    distribution: Dict[str, Any],
    monthly_traffic_gb: float,
) -> str:
    """
    Build the human-readable recommendation.
    """

    distribution_id = distribution.get(
        "Id",
        "unknown",
    )

    domain_name = distribution.get(
        "DomainName",
        "",
    )

    return (
        f"Review viewer geography for CloudFront distribution "
        f"'{distribution_id}' ({domain_name}). "
        f"The distribution is currently using PriceClass_All "
        f"and serves approximately "
        f"{monthly_traffic_gb:.2f} GB/month. "
        f"Validate that viewers require all CloudFront edge "
        f"locations. If appropriate, change the distribution "
        f"to PriceClass_100 to reduce delivery costs."
    )


# ============================================================
# 11. MESSAGE
# ============================================================

def build_message(
    distribution: Dict[str, Any],
    monthly_traffic_gb: float,
) -> str:
    """
    Explain why the resource was identified.
    """

    distribution_id = distribution.get(
        "Id",
        "unknown",
    )

    price_class = distribution.get(
        "PriceClass",
        "unknown",
    )

    return (
        f"CloudFront distribution '{distribution_id}' "
        f"is using {price_class} and is serving approximately "
        f"{monthly_traffic_gb:.2f} GB/month. "
        f"The distribution may be using higher-cost edge "
        f"locations than required."
    )


# ============================================================
# 12. ESTIMATED SAVINGS
# ============================================================

def calculate_estimated_monthly_savings(
    current_monthly_cost: Optional[float],
) -> Optional[float]:
    """
    Calculate an approximate savings amount using the configured
    premium-region traffic assumption.

    This calculation is intentionally disabled when no current
    monthly cost is available.

    CUR/Athena is NOT used here.
    """

    if current_monthly_cost is None:
        return None

    if ASSUMED_PREMIUM_REGION_SHARE is None:
        return None

    return round(
        current_monthly_cost
        * ASSUMED_PREMIUM_REGION_SHARE,
        2,
    )


# ============================================================
# 13. BUILD FINDING
# ============================================================

def build_finding(
    account_id: str,
    region_name: str,
    distribution: Dict[str, Any],
    monthly_traffic_gb: float,
    current_daily_cost: Optional[float] = None,
    current_monthly_cost: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Build the standardized root finding schema.

    Service-specific information is retained in the finding and
    will later be moved into the description column by the Excel
    exporter.
    """

    distribution_id = distribution.get(
        "Id",
    )

    distribution_arn = distribution.get(
        "ARN",
    )

    domain_name = distribution.get(
        "DomainName",
    )

    price_class = distribution.get(
        "PriceClass",
    )

    enabled = distribution.get(
        "Enabled",
    )

    status = distribution.get(
        "Status",
    )

    comment = distribution.get(
        "Comment",
        "",
    )

    aliases = (
        distribution
        .get("Aliases", {})
        .get("Items", [])
    )

    message = build_message(
        distribution=distribution,
        monthly_traffic_gb=monthly_traffic_gb,
    )

    recommendation = build_recommendation(
        distribution=distribution,
        monthly_traffic_gb=monthly_traffic_gb,
    )

    estimated_monthly_savings = (
        calculate_estimated_monthly_savings(
            current_monthly_cost=current_monthly_cost,
        )
    )

    return {
        # Standard workflow fields
        "workItemType": "Task",
        "state": "To Do",
        "id": None,
        "title": CATEGORY,
        "category": CATEGORY,
        "owner": "",
        "assignedTo": "",
        "status": "Review Required",
        "areaPath": "AWS Cost Optimization",
        "tags": "CLX",
        "commentCount": 0,

        # AWS identification
        "accountId": account_id,
        "region": region_name,
        "resourceNameOrId": distribution_id,
        "resourceId": distribution_id,
        "resourceArn": distribution_arn,

        # Service information
        "service": SERVICE_NAME,
        "type": "Optimization Description",
        "policy": POLICY_NAME,
        "effortLevel": EFFORT_LEVEL,

        # Recommendation
        "message": message,
        "recommendation": recommendation,

        # Cost
        "currentDailyCost": current_daily_cost,
        "currentMonthlyCost": current_monthly_cost,
        "estimatedMonthlySavings": estimated_monthly_savings,

        # Workflow fields
        "approvalComments": "",
        "reasonForRejection": "",
        "achievedSavingsMonthly": None,
        "month": "",

        # Service-specific attributes
        "distributionId": distribution_id,
        "distributionArn": distribution_arn,
        "domainName": domain_name,
        "priceClass": price_class,
        "enabled": enabled,
        "distributionStatus": status,
        "monthlyTrafficGB": round(
            monthly_traffic_gb,
            2,
        ),
        "lookbackDays": LOOKBACK_DAYS,
        "minimumTrafficThresholdGB": (
            MIN_MONTHLY_TRAFFIC_GB
        ),
        "assumedPremiumRegionShare": (
            ASSUMED_PREMIUM_REGION_SHARE
        ),
        "aliases": aliases,
        "comment": comment,
    }


# ============================================================
# 14. EXCEL EXPORTER
# ============================================================

def export_to_excel(
    findings: List[Dict[str, Any]],
    filename: str,
) -> None:
    """
    Export findings using the strict 30-column schema.

    Any service-specific keys are bundled into the description
    column as pipe-separated key/value pairs.
    """

    flat_findings: List[Dict[str, Any]] = []

    for finding in findings:

        standard_data: Dict[str, Any] = {}

        extra_attributes: List[str] = []

        for key, value in finding.items():

            if key in STANDARD_COLUMNS:

                standard_data[key] = value

            else:

                if value is None:
                    continue

                if isinstance(value, (dict, list)):

                    value_string = json.dumps(
                        value,
                        default=str,
                    )

                else:

                    value_string = str(
                        value,
                    )

                extra_attributes.append(
                    f"{key}: {value_string}"
                )

        # Existing description
        description = standard_data.get(
            "description",
            "",
        )

        # Add service-specific fields
        if extra_attributes:

            extra_description = " | ".join(
                extra_attributes
            )

            if description:

                description = (
                    f"{description} | "
                    f"{extra_description}"
                )

            else:

                description = (
                    extra_description
                )

        standard_data["description"] = description

        flat_findings.append(
            standard_data
        )

    df = pd.DataFrame(
        flat_findings,
        columns=STANDARD_COLUMNS,
    )

    df.to_excel(
        filename,
        index=False,
    )

    print(
        f"[INFO] Excel report generated: {filename}"
    )


# ============================================================
# 15. MAIN SCANNER
# ============================================================

def scan_service(
    region_name: str = CLOUDFRONT_REGION,
) -> Dict[str, Any]:
    """
    Main CloudFront scanner.

    One failed distribution does not stop the entire scan.
    """

    cloudfront, cloudwatch, sts = create_clients(
        region_name=region_name,
    )

    account_id = get_account_id(
        sts,
    )

    findings: List[Dict[str, Any]] = []

    distributions_scanned = 0

    candidate_count = 0

    distributions = fetch_all_distributions(
        cloudfront,
    )

    print(
        f"[INFO] CloudFront distributions found: "
        f"{len(distributions)}"
    )

    for distribution_summary in distributions:

        distribution_id = distribution_summary.get(
            "Id",
        )

        if not distribution_id:
            continue

        distributions_scanned += 1

        try:

            distribution = get_distribution_details(
                cloudfront=cloudfront,
                distribution_id=distribution_id,
            )

            total_bytes = get_bytes_downloaded(
                cloudwatch=cloudwatch,
                distribution_id=distribution_id,
                lookback_days=LOOKBACK_DAYS,
            )

            monthly_traffic_gb = (
                calculate_monthly_traffic_gb(
                    total_bytes=total_bytes,
                    lookback_days=LOOKBACK_DAYS,
                )
            )

            print(
                f"[INFO] {distribution_id} | "
                f"PriceClass="
                f"{distribution.get('PriceClass')} | "
                f"Traffic="
                f"{monthly_traffic_gb:.2f} GB/month"
            )

            if not is_candidate(
                distribution=distribution,
                monthly_traffic_gb=monthly_traffic_gb,
            ):
                continue

            finding = build_finding(
                account_id=account_id,
                region_name=GLOBAL_REGION,
                distribution=distribution,
                monthly_traffic_gb=monthly_traffic_gb,

                # CUR/Athena is intentionally not used.
                current_daily_cost=None,
                current_monthly_cost=None,
            )

            findings.append(
                finding
            )

            candidate_count += 1

        except ClientError as exc:

            print(
                f"[ERROR] Failed processing "
                f"distribution {distribution_id}: "
                f"{exc}"
            )

            continue

        except Exception as exc:

            print(
                f"[ERROR] Unexpected error processing "
                f"distribution {distribution_id}: "
                f"{exc}"
            )

            continue

    return {
        "accountId": account_id,
        "region": GLOBAL_REGION,
        "service": SERVICE_NAME,
        "policy": POLICY_NAME,
        "lookbackDays": LOOKBACK_DAYS,
        "totalDistributionsScanned": (
            distributions_scanned
        ),
        "totalCandidates": candidate_count,
        "findings": findings,
    }


# ============================================================
# 16. ENTRY POINT
# ============================================================

if __name__ == "__main__":

    region = CLOUDFRONT_REGION

    result = scan_service(
        region_name=region,
    )

    print(
        json.dumps(
            result,
            indent=2,
            default=str,
        )
    )

    export_to_excel(
        findings=result.get(
            "findings",
            [],
        ),
        filename=(
            "cloudfront_price_class_oversized.xlsx"
        ),
    )