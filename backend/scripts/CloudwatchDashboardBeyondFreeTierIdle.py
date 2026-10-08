from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3

from botocore.config import Config
from botocore.exceptions import ClientError

import pandas as pd
import json


# ============================================================
# 1. IMPORTS
# ============================================================


# ============================================================
# 2. AWS CLIENT CONFIGURATION
# ============================================================

AWS_CONFIG = Config(
    retries={
        "mode": "adaptive",
        "max_attempts": 10,
    }
)


# ============================================================
# 3. FINOPS POLICY CONFIGURATION
# ============================================================

POLICY_NAME = (
    "Cloudwatch Dashboard Beyond Free Tier Idle"
)

CATEGORY = (
    "Cloudwatch Dashboard Beyond Free Tier Idle"
)

SERVICE_NAME = "CloudWatch"

EFFORT_LEVEL = "Low"

DEFAULT_REGION = "eu-west-1"


# ------------------------------------------------------------
# Dashboard policy thresholds
# ------------------------------------------------------------

# Number of CloudWatch dashboards included in the configured
# free tier.
#
# This is configurable because pricing/free-tier terms can
# change and may depend on the account/plan.
FREE_DASHBOARD_COUNT = 3


# Number of days without modification before a dashboard is
# considered idle.
#
# Example:
#
# 610 days > 180 days
# -> idle candidate
IDLE_DAYS_THRESHOLD = 180


# ============================================================
# 4. STANDARD EXCEL COLUMNS
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
# 5. AWS CLIENTS
# ============================================================

def create_clients(
    region_name: str,
):
    """
    Create CloudWatch and STS clients.
    """

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

    return cloudwatch, sts


def get_account_id(
    sts,
) -> str:
    """
    Return the AWS account ID.
    """

    return sts.get_caller_identity()["Account"]


# ============================================================
# 6. FETCH ALL DASHBOARDS
# ============================================================

def fetch_all_dashboards(
    cloudwatch,
) -> List[Dict[str, Any]]:
    """
    Fetch all CloudWatch dashboards using the Boto3 paginator.

    ListDashboards is paginated, so all pages are processed.
    """

    dashboards: List[
        Dict[str, Any]
    ] = []

    paginator = cloudwatch.get_paginator(
        "list_dashboards"
    )

    for page in paginator.paginate():

        page_dashboards = page.get(
            "DashboardEntries",
            [],
        )

        dashboards.extend(
            page_dashboards
        )

    return dashboards


# ============================================================
# 7. DATETIME NORMALIZATION
# ============================================================

def normalize_datetime(
    value: Any,
) -> Optional[datetime]:
    """
    Normalize an AWS datetime value into a timezone-aware
    datetime.

    AWS boto3 datetime values are normally already timezone
    aware, but this function also handles strings.
    """

    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):

        if value.tzinfo is None:

            return value.replace(
                tzinfo=timezone.utc
            )

        return value

    if isinstance(
        value,
        str,
    ):

        try:

            parsed = datetime.fromisoformat(
                value.replace(
                    "Z",
                    "+00:00",
                )
            )

            if parsed.tzinfo is None:

                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed

        except ValueError:

            return None

    return None


# ============================================================
# 8. CALCULATE DASHBOARD AGE
# ============================================================

def calculate_idle_days(
    last_modified: Any,
) -> Optional[int]:
    """
    Calculate how many days have passed since the dashboard
    was last modified.
    """

    last_modified_datetime = (
        normalize_datetime(
            last_modified
        )
    )

    if last_modified_datetime is None:
        return None

    now = datetime.now(
        timezone.utc
    )

    age = (
        now
        - last_modified_datetime
    )

    return max(
        0,
        age.days,
    )


# ============================================================
# 9. BUSINESS LOGIC
# ============================================================

def is_idle_dashboard(
    dashboard: Dict[str, Any],
) -> bool:
    """
    Determine whether a dashboard has been idle beyond the
    configured threshold.
    """

    idle_days = calculate_idle_days(
        dashboard.get(
            "LastModified"
        )
    )

    if idle_days is None:
        return False

    return (
        idle_days
        >= IDLE_DAYS_THRESHOLD
    )


# ============================================================
# 10. FREE-TIER LOGIC
# ============================================================

def is_beyond_free_tier(
    total_dashboard_count: int,
) -> bool:
    """
    Determine whether the account has more dashboards than
    the configured free-tier allowance.
    """

    return (
        total_dashboard_count
        > FREE_DASHBOARD_COUNT
    )


def get_billable_dashboard_count(
    total_dashboard_count: int,
) -> int:
    """
    Calculate the number of dashboards beyond the configured
    free-tier allowance.
    """

    return max(
        0,
        total_dashboard_count
        - FREE_DASHBOARD_COUNT,
    )


# ============================================================
# 11. IDENTIFY IDLE BILLABLE DASHBOARDS
# ============================================================

def find_idle_billable_dashboards(
    dashboards: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Identify dashboards that are:

        1. Beyond the configured free-tier count
        2. Idle beyond the configured idle threshold

    The oldest dashboards are considered the most appropriate
    candidates when the account has more dashboards than the
    free-tier allowance.

    The function sorts dashboards by LastModified ascending,
    meaning oldest dashboards appear first.
    """

    total_dashboard_count = len(
        dashboards
    )

    if not is_beyond_free_tier(
        total_dashboard_count
    ):

        return []

    sorted_dashboards = sorted(
        dashboards,
        key=lambda dashboard: (
            normalize_datetime(
                dashboard.get(
                    "LastModified"
                )
            )
            or datetime.max.replace(
                tzinfo=timezone.utc
            )
        ),
    )

    billable_count = (
        get_billable_dashboard_count(
            total_dashboard_count
        )
    )

    candidates: List[
        Dict[str, Any]
    ] = []

    # --------------------------------------------------------
    # Important:
    #
    # We inspect the oldest dashboards first because the
    # account has more dashboards than its free-tier allowance.
    #
    # Only idle dashboards are returned.
    # --------------------------------------------------------

    for dashboard in sorted_dashboards:

        if not is_idle_dashboard(
            dashboard
        ):
            continue

        candidates.append(
            dashboard
        )

        # Once we have identified the number of dashboards
        # beyond the free-tier allowance, there is no need to
        # flag additional dashboards as "beyond free tier".
        if len(candidates) >= billable_count:
            break

    return candidates


# ============================================================
# 12. BUILD MESSAGE
# ============================================================

def build_message(
    dashboard: Dict[str, Any],
    total_dashboard_count: int,
    billable_dashboard_count: int,
) -> str:
    """
    Build the human-readable explanation.
    """

    dashboard_name = dashboard.get(
        "DashboardName",
        "unknown",
    )

    idle_days = calculate_idle_days(
        dashboard.get(
            "LastModified"
        )
    )

    if idle_days is None:

        idle_text = (
            "its last modification date could not be "
            "determined"
        )

    else:

        idle_text = (
            f"it has not been modified for "
            f"{idle_days} days"
        )

    return (
        f"CloudWatch dashboard '{dashboard_name}' "
        f"is idle because {idle_text}. "
        f"The account currently has "
        f"{total_dashboard_count} dashboards, "
        f"which is above the configured free-tier allowance "
        f"of {FREE_DASHBOARD_COUNT}. "
        f"{billable_dashboard_count} dashboard(s) are "
        f"therefore beyond the configured allowance."
    )


# ============================================================
# 13. BUILD RECOMMENDATION
# ============================================================

def build_recommendation(
    dashboard: Dict[str, Any],
) -> str:
    """
    Build the human-readable remediation recommendation.
    """

    dashboard_name = dashboard.get(
        "DashboardName",
        "unknown",
    )

    return (
        f"Review CloudWatch dashboard '{dashboard_name}' "
        f"with the application and monitoring owners. "
        f"If the dashboard is no longer required, delete it "
        f"using the CloudWatch DeleteDashboards API. "
        f"Before deletion, confirm that no operational or "
        f"business monitoring process depends on it."
    )


# ============================================================
# 14. BUILD FINDING
# ============================================================

def build_finding(
    account_id: str,
    region_name: str,
    dashboard: Dict[str, Any],
    total_dashboard_count: int,
    billable_dashboard_count: int,
) -> Dict[str, Any]:
    """
    Build the standardized FinOps finding.

    Dashboard-specific fields are retained here and will be
    bundled into the description column by export_to_excel().
    """

    dashboard_name = dashboard.get(
        "DashboardName"
    )

    dashboard_arn = dashboard.get(
        "DashboardArn"
    )

    last_modified = dashboard.get(
        "LastModified"
    )

    dashboard_size = dashboard.get(
        "Size"
    )

    idle_days = calculate_idle_days(
        last_modified
    )

    return {
        # ----------------------------------------------------
        # Standard workflow fields
        # ----------------------------------------------------

        "workItemType": "Task",

        "state": "To Do",

        "id": None,

        "title": CATEGORY,

        "category": CATEGORY,

        "owner": "",

        "assignedTo": "",

        "status": "Pending for Review",

        "areaPath": "AWS Cost Optimization",

        "tags": "DevOps",

        "commentCount": 0,

        # ----------------------------------------------------
        # AWS information
        # ----------------------------------------------------

        "accountId": account_id,

        "region": region_name,

        "resourceNameOrId": dashboard_name,

        "resourceId": dashboard_name,

        "resourceArn": dashboard_arn,

        # ----------------------------------------------------
        # Service information
        # ----------------------------------------------------

        "service": SERVICE_NAME,

        "type": "Optimization Description",

        "policy": POLICY_NAME,

        "effortLevel": EFFORT_LEVEL,

        # ----------------------------------------------------
        # Finding
        # ----------------------------------------------------

        "message": build_message(
            dashboard=dashboard,
            total_dashboard_count=(
                total_dashboard_count
            ),
            billable_dashboard_count=(
                billable_dashboard_count
            ),
        ),

        "recommendation": build_recommendation(
            dashboard
        ),

        # ----------------------------------------------------
        # Cost
        #
        # CUR/Athena intentionally not used.
        # ----------------------------------------------------

        "currentDailyCost": None,

        "currentMonthlyCost": None,

        "estimatedMonthlySavings": None,

        # ----------------------------------------------------
        # Workflow fields
        # ----------------------------------------------------

        "approvalComments": "",

        "reasonForRejection": "",

        "achievedSavingsMonthly": None,

        "month": "",

        # ----------------------------------------------------
        # Service-specific attributes
        # ----------------------------------------------------

        "dashboardName": dashboard_name,

        "dashboardArn": dashboard_arn,

        "lastModified": last_modified,

        "idleDays": idle_days,

        "idleDaysThreshold": (
            IDLE_DAYS_THRESHOLD
        ),

        "totalDashboards": (
            total_dashboard_count
        ),

        "freeDashboardCount": (
            FREE_DASHBOARD_COUNT
        ),

        "billableDashboardCount": (
            billable_dashboard_count
        ),

        "dashboardSizeBytes": (
            dashboard_size
        ),
    }


# ============================================================
# 15. EXCEL EXPORTER
# ============================================================

def export_to_excel(
    findings: List[Dict[str, Any]],
    filename: str,
) -> None:
    """
    Export findings using exactly the 30 standard columns.

    All service-specific attributes are dynamically bundled
    into the description column.
    """

    flat_findings: List[
        Dict[str, Any]
    ] = []

    for finding in findings:

        standard_data: Dict[
            str,
            Any,
        ] = {}

        extra_attributes: List[
            str
        ] = []

        for key, value in finding.items():

            if key in STANDARD_COLUMNS:

                standard_data[key] = value

            else:

                if value is None:
                    continue

                if isinstance(
                    value,
                    (dict, list),
                ):

                    value_string = json.dumps(
                        value,
                        default=str,
                    )

                else:

                    value_string = str(
                        value
                    )

                extra_attributes.append(
                    f"{key}: {value_string}"
                )

        existing_description = (
            standard_data.get(
                "description",
                "",
            )
        )

        if extra_attributes:

            extra_description = (
                " | ".join(
                    extra_attributes
                )
            )

            if existing_description:

                standard_data[
                    "description"
                ] = (
                    f"{existing_description} | "
                    f"{extra_description}"
                )

            else:

                standard_data[
                    "description"
                ] = extra_description

        else:

            standard_data[
                "description"
            ] = existing_description

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
        f"[INFO] Excel report generated: "
        f"{filename}"
    )


# ============================================================
# 16. MAIN SCANNER
# ============================================================

def scan_service(
    region_name: str = DEFAULT_REGION,
) -> Dict[str, Any]:
    """
    Main CloudWatch Dashboard Beyond Free Tier Idle scanner.
    """

    cloudwatch, sts = create_clients(
        region_name=region_name,
    )

    account_id = get_account_id(
        sts
    )

    print(
        f"[INFO] Scanning CloudWatch dashboards "
        f"in {region_name}..."
    )

    # --------------------------------------------------------
    # Fetch dashboards
    # --------------------------------------------------------

    dashboards = fetch_all_dashboards(
        cloudwatch
    )

    total_dashboard_count = len(
        dashboards
    )

    print(
        f"[INFO] Total CloudWatch dashboards: "
        f"{total_dashboard_count}"
    )

    # --------------------------------------------------------
    # Free-tier calculation
    # --------------------------------------------------------

    billable_dashboard_count = (
        get_billable_dashboard_count(
            total_dashboard_count
        )
    )

    print(
        f"[INFO] Configured free dashboards: "
        f"{FREE_DASHBOARD_COUNT}"
    )

    print(
        f"[INFO] Dashboards beyond allowance: "
        f"{billable_dashboard_count}"
    )

    # --------------------------------------------------------
    # Find idle billable dashboards
    # --------------------------------------------------------

    candidate_dashboards = (
        find_idle_billable_dashboards(
            dashboards
        )
    )

    findings: List[
        Dict[str, Any]
    ] = []

    candidates = 0

    for dashboard in candidate_dashboards:

        dashboard_name = dashboard.get(
            "DashboardName",
            "unknown",
        )

        try:

            finding = build_finding(
                account_id=account_id,
                region_name=region_name,
                dashboard=dashboard,
                total_dashboard_count=(
                    total_dashboard_count
                ),
                billable_dashboard_count=(
                    billable_dashboard_count
                ),
            )

            findings.append(
                finding
            )

            candidates += 1

            idle_days = calculate_idle_days(
                dashboard.get(
                    "LastModified"
                )
            )

            print(
                f"[FINDING] Idle CloudWatch dashboard: "
                f"{dashboard_name} | "
                f"Idle days: {idle_days}"
            )

        except ClientError as exc:

            print(
                f"[ERROR] Failed processing dashboard "
                f"{dashboard_name}: {exc}"
            )

            continue

        except Exception as exc:

            print(
                f"[ERROR] Unexpected error processing "
                f"dashboard {dashboard_name}: {exc}"
            )

            continue

    return {
        "accountId": account_id,

        "region": region_name,

        "service": SERVICE_NAME,

        "policy": POLICY_NAME,

        "totalDashboardsScanned": (
            total_dashboard_count
        ),

        "freeDashboardCount": (
            FREE_DASHBOARD_COUNT
        ),

        "billableDashboardCount": (
            billable_dashboard_count
        ),

        "idleDaysThreshold": (
            IDLE_DAYS_THRESHOLD
        ),

        "totalCandidates": candidates,

        "findings": findings,
    }


# ============================================================
# 17. ENTRY POINT
# ============================================================

if __name__ == "__main__":

    region = DEFAULT_REGION

    result = scan_service(
        region_name=region
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
            "cloudwatch_dashboard_beyond_free_tier_idle.xlsx"
        ),
    )