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


# ------------------------------------------------------------
# CloudWatch dashboards are global resources.
#
# They are NOT Region-specific.
#
# Therefore the scanner does not need to scan every AWS Region.
# ------------------------------------------------------------

RESOURCE_REGION = "global"


# ------------------------------------------------------------
# Cross-account configuration
# ------------------------------------------------------------

# The AWS account IDs that should be scanned.
#
# The credentials used to run this script must have permission
# to assume the configured role in these accounts.
#
# Example:
#
# ACCOUNT_IDS = [
#     "891150219266",
#     "339712988055",
#     "642138000000",
# ]
#
ACCOUNT_IDS: List[str] = [
    "675134942214",
]


# ------------------------------------------------------------
# Cross-account IAM role
# ------------------------------------------------------------

# This role must exist in every target account.
#
# Example trust relationship:
#
# Scanner Account
#       |
#       | sts:AssumeRole
#       v
# Target Account
#       |
#       └── FinOpsReadOnlyRole
#
ASSUME_ROLE_NAME = "FinOpsReadOnlyRole"


# ------------------------------------------------------------
# Assume-role session configuration
# ------------------------------------------------------------

ASSUME_ROLE_SESSION_NAME = (
    "FinOpsCloudWatchDashboardScanner"
)


# ------------------------------------------------------------
# Dashboard policy thresholds
# ------------------------------------------------------------

# AWS CloudWatch currently provides 3 custom dashboards
# referencing up to 50 metrics each per account per month
# in the free tier.
#
# Keep this configurable so the policy can be changed if AWS
# pricing/free-tier rules change.
FREE_DASHBOARD_COUNT = 3


# Dashboard idle threshold.
#
# Example:
#
# Dashboard last modified 610 days ago
# threshold = 180 days
#
# 610 >= 180
# -> candidate
IDLE_DAYS_THRESHOLD = 0


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

def create_base_sts_client():
    """
    Create the STS client using the credentials under which
    this scanner is executed.

    These credentials are used to assume the cross-account
    FinOpsReadOnlyRole in each target account.
    """

    return boto3.client(
        "sts",
        config=AWS_CONFIG,
    )


def assume_target_account_role(
    base_sts,
    account_id: str,
):
    """
    Assume the FinOpsReadOnlyRole in the target AWS account.

    The target account must have a role named:

        FinOpsReadOnlyRole

    and the source scanning account/user/role must be trusted
    by that role.
    """

    role_arn = (
        f"arn:aws:iam::{account_id}:role/"
        f"{ASSUME_ROLE_NAME}"
    )

    try:

        response = base_sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName=(
                f"{ASSUME_ROLE_SESSION_NAME}-"
                f"{account_id}"
            ),
        )

        credentials = response[
            "Credentials"
        ]

        return credentials

    except ClientError as exc:

        print(
            f"[ERROR] Unable to assume role in "
            f"account {account_id}: {exc}"
        )

        return None


def create_target_account_clients(
    credentials,
):
    """
    Create CloudWatch and STS clients using temporary
    credentials from the target account.

    CloudWatch dashboards are global, but the CloudWatch
    client still requires a Region endpoint.

    us-east-1 is used only as the API endpoint.
    It does NOT mean the dashboards belong to us-east-1.
    """

    if credentials is None:
        session = boto3.Session()
    else:
        session = boto3.Session(
            aws_access_key_id=(
                credentials["AccessKeyId"]
            ),
            aws_secret_access_key=(
                credentials["SecretAccessKey"]
            ),
            aws_session_token=(
                credentials["SessionToken"]
            ),
        )

    cloudwatch = session.client(
        "cloudwatch",
        region_name="us-east-1",
        config=AWS_CONFIG,
    )

    sts = session.client(
        "sts",
        region_name="us-east-1",
        config=AWS_CONFIG,
    )

    return cloudwatch, sts


def get_account_id(
    sts,
) -> str:
    """
    Return the AWS account ID associated with the
    currently assumed credentials.
    """

    return sts.get_caller_identity()[
        "Account"
    ]


# ============================================================
# 6. FETCH ALL DASHBOARDS
# ============================================================

def fetch_all_dashboards(
    cloudwatch,
) -> List[Dict[str, Any]]:
    """
    Fetch every CloudWatch dashboard in the account.

    ListDashboards is paginated, therefore get_paginator()
    is mandatory for complete discovery.
    """

    dashboards: List[
        Dict[str, Any]
    ] = []

    paginator = cloudwatch.get_paginator(
        "list_dashboards"
    )

    try:

        for page in paginator.paginate():

            page_dashboards = page.get(
                "DashboardEntries",
                [],
            )

            dashboards.extend(
                page_dashboards
            )

    except ClientError as exc:

        print(
            f"[ERROR] Failed to list CloudWatch "
            f"dashboards: {exc}"
        )

        raise

    return dashboards


# ============================================================
# 7. DATETIME HANDLING
# ============================================================

def normalize_datetime(
    value: Any,
) -> Optional[datetime]:
    """
    Normalize AWS datetime values into timezone-aware UTC
    datetime objects.

    Boto3 normally returns datetime objects for LastModified.
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

        return value.astimezone(
            timezone.utc
        )

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

            return parsed.astimezone(
                timezone.utc
            )

        except ValueError:

            return None

    return None


# ============================================================
# 8. DASHBOARD AGE CALCULATION
# ============================================================

def calculate_idle_days(
    last_modified: Any,
) -> Optional[int]:
    """
    Calculate the number of complete days since the dashboard
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

    elapsed = (
        now
        - last_modified_datetime
    )

    return max(
        0,
        elapsed.days,
    )


# ============================================================
# 9. BUSINESS LOGIC
# ============================================================

def is_idle_dashboard(
    dashboard: Dict[str, Any],
) -> bool:
    """
    Return True when a dashboard has not been modified for
    at least IDLE_DAYS_THRESHOLD days.
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


def get_billable_dashboard_count(
    total_dashboard_count: int,
) -> int:
    """
    Calculate the number of dashboards beyond the configured
    free-tier allowance.

    This calculation is performed independently for each AWS
    account.
    """

    return max(
        0,
        total_dashboard_count
        - FREE_DASHBOARD_COUNT,
    )


def identify_billable_idle_dashboards(
    dashboards: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Identify dashboards that are both:

        1. Beyond the account's free-tier allowance.
        2. Idle beyond IDLE_DAYS_THRESHOLD.

    Dashboards are sorted from oldest to newest.

    This means the oldest dashboards are considered first when
    determining which dashboards are beyond the allowance.
    """

    total_dashboard_count = len(
        dashboards
    )

    billable_dashboard_count = (
        get_billable_dashboard_count(
            total_dashboard_count
        )
    )

    if billable_dashboard_count <= 0:

        return []

    # --------------------------------------------------------
    # Oldest dashboards first.
    # --------------------------------------------------------

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

    candidates: List[
        Dict[str, Any]
    ] = []

    # --------------------------------------------------------
    # Only the dashboards beyond the free allowance are
    # considered billable.
    #
    # Among them, only idle dashboards are findings.
    # --------------------------------------------------------

    for dashboard in sorted_dashboards:

        if len(candidates) >= (
            billable_dashboard_count
        ):

            break

        if not is_idle_dashboard(
            dashboard
        ):

            continue

        candidates.append(
            dashboard
        )

    return candidates


# ============================================================
# 10. BUILD MESSAGE
# ============================================================

def build_message(
    dashboard: Dict[str, Any],
    total_dashboard_count: int,
    billable_dashboard_count: int,
) -> str:
    """
    Build the standardized finding message.
    """

    dashboard_name = dashboard.get(
        "DashboardName",
        "Unknown",
    )

    idle_days = calculate_idle_days(
        dashboard.get(
            "LastModified"
        )
    )

    if idle_days is None:

        idle_text = (
            "the last modification date could not "
            "be determined"
        )

    else:

        idle_text = (
            f"it has not been modified for "
            f"{idle_days} days"
        )

    return (
        f"CloudWatch dashboard "
        f"'{dashboard_name}' is idle because "
        f"{idle_text}. "
        f"The account has "
        f"{total_dashboard_count} custom dashboards "
        f"and the configured free-tier allowance is "
        f"{FREE_DASHBOARD_COUNT}. "
        f"{billable_dashboard_count} dashboard(s) "
        f"are beyond the free-tier allowance."
    )


# ============================================================
# 11. BUILD RECOMMENDATION
# ============================================================

def build_recommendation(
    dashboard: Dict[str, Any],
) -> str:
    """
    Build remediation instructions.
    """

    dashboard_name = dashboard.get(
        "DashboardName",
        "Unknown",
    )

    return (
        f"Review CloudWatch dashboard "
        f"'{dashboard_name}' with the application, "
        f"operations, and monitoring owners. "
        f"If the dashboard is no longer required, "
        f"delete it using the CloudWatch "
        f"DeleteDashboards API. "
        f"Before deletion, confirm that no operational, "
        f"business, or compliance monitoring process "
        f"depends on the dashboard."
    )


# ============================================================
# 12. BUILD FINDING
# ============================================================

def build_finding(
    account_id: str,
    dashboard: Dict[str, Any],
    total_dashboard_count: int,
    billable_dashboard_count: int,
) -> Dict[str, Any]:
    """
    Build the standardized FinOps finding.

    CloudWatch dashboards are global resources, so region is
    always represented as "global".
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
        # ====================================================
        # Workflow
        # ====================================================

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

        # ====================================================
        # AWS
        # ====================================================

        "accountId": account_id,

        "region": RESOURCE_REGION,

        "resourceNameOrId": dashboard_arn,

        "resourceId": dashboard_name,

        "resourceArn": dashboard_arn,

        # ====================================================
        # Service
        # ====================================================

        "service": SERVICE_NAME,

        "type": "Optimization Description",

        "policy": POLICY_NAME,

        "effortLevel": EFFORT_LEVEL,

        # ====================================================
        # Finding
        # ====================================================

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

        # ====================================================
        # Cost
        #
        # CUR/Athena intentionally not used.
        # ====================================================

        "currentDailyCost": None,

        "currentMonthlyCost": None,

        "estimatedMonthlySavings": None,

        # ====================================================
        # Workflow tracking
        # ====================================================

        "approvalComments": "",

        "reasonForRejection": "",

        "achievedSavingsMonthly": None,

        "month": "",

        # ====================================================
        # Service-specific fields
        #
        # These will automatically be bundled into
        # description by export_to_excel().
        # ====================================================

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
# 13. EXCEL EXPORTER
# ============================================================

def export_to_excel(
    findings: List[Dict[str, Any]],
    filename: str,
) -> None:
    """
    Export findings using exactly the 30 standard columns.

    Any service-specific fields are dynamically serialized
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

        # ----------------------------------------------------
        # Separate standard and service-specific fields
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Build description
        # ----------------------------------------------------

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

    # --------------------------------------------------------
    # Create dataframe with EXACT column ordering.
    # --------------------------------------------------------

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
# 14. SCAN ONE AWS ACCOUNT
# ============================================================

def scan_account(
    base_sts,
    target_account_id: str,
) -> Dict[str, Any]:
    """
    Scan CloudWatch dashboards in one target account.

    This function is intentionally isolated so that one
    account failure does not terminate the complete
    multi-account scan.
    """

    print()
    print(
        "=" * 70
    )

    print(
        f"[INFO] Starting account scan: "
        f"{target_account_id}"
    )

    print(
        "=" * 70
    )

    # --------------------------------------------------------
    # Assume target account role (skip for local account)
    # --------------------------------------------------------
    
    base_account_id = get_account_id(base_sts)
    
    if target_account_id == base_account_id:
        print(f"[INFO] Bypassing AssumeRole for local account {target_account_id}")
        credentials = None
    else:
        credentials = (
            assume_target_account_role(
                base_sts=base_sts,
                account_id=target_account_id,
            )
        )

        if credentials is None:

            return {
                "accountId": target_account_id,
                "success": False,
                "totalDashboardsScanned": 0,
                "totalCandidates": 0,
                "findings": [],
                "error": (
                    "Unable to assume target account role"
                ),
            }

    try:

        cloudwatch, sts = (
            create_target_account_clients(
                credentials
            )
        )

        actual_account_id = get_account_id(
            sts
        )

        # ----------------------------------------------------
        # Safety check.
        #
        # The assumed role should resolve to the requested
        # account.
        # ----------------------------------------------------

        if actual_account_id != target_account_id:

            error_message = (
                f"Account mismatch. Requested "
                f"{target_account_id}, but assumed "
                f"credentials belong to "
                f"{actual_account_id}."
            )

            print(
                f"[ERROR] {error_message}"
            )

            return {
                "accountId": target_account_id,
                "success": False,
                "totalDashboardsScanned": 0,
                "totalCandidates": 0,
                "findings": [],
                "error": error_message,
            }

        # ----------------------------------------------------
        # Fetch dashboards
        # ----------------------------------------------------

        dashboards = fetch_all_dashboards(
            cloudwatch
        )

        total_dashboard_count = len(
            dashboards
        )

        # ----------------------------------------------------
        # Calculate account-level free tier
        # ----------------------------------------------------

        billable_dashboard_count = (
            get_billable_dashboard_count(
                total_dashboard_count
            )
        )

        print(
            f"[INFO] Account: "
            f"{actual_account_id}"
        )

        print(
            f"[INFO] Dashboards discovered: "
            f"{total_dashboard_count}"
        )

        print(
            f"[INFO] Free dashboard allowance: "
            f"{FREE_DASHBOARD_COUNT}"
        )

        print(
            f"[INFO] Dashboards beyond allowance: "
            f"{billable_dashboard_count}"
        )

        # ----------------------------------------------------
        # Identify idle dashboards
        # ----------------------------------------------------

        candidate_dashboards = (
            identify_billable_idle_dashboards(
                dashboards
            )
        )

        findings: List[
            Dict[str, Any]
        ] = []

        for dashboard in candidate_dashboards:

            dashboard_name = dashboard.get(
                "DashboardName",
                "Unknown",
            )

            try:

                finding = build_finding(
                    account_id=actual_account_id,
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

                idle_days = (
                    calculate_idle_days(
                        dashboard.get(
                            "LastModified"
                        )
                    )
                )

                print(
                    f"[FINDING] Account="
                    f"{actual_account_id} | "
                    f"Dashboard="
                    f"{dashboard_name} | "
                    f"IdleDays="
                    f"{idle_days}"
                )

            except Exception as exc:

                print(
                    f"[ERROR] Failed processing "
                    f"dashboard "
                    f"'{dashboard_name}' "
                    f"in account "
                    f"{actual_account_id}: "
                    f"{exc}"
                )

                continue

        print(
            f"[INFO] Account scan completed: "
            f"{actual_account_id} | "
            f"Candidates={len(findings)}"
        )

        return {
            "accountId": actual_account_id,

            "success": True,

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

            "totalCandidates": len(
                findings
            ),

            "findings": findings,
        }

    except ClientError as exc:

        print(
            f"[ERROR] AWS error while scanning "
            f"account {target_account_id}: "
            f"{exc}"
        )

        return {
            "accountId": target_account_id,
            "success": False,
            "totalDashboardsScanned": 0,
            "totalCandidates": 0,
            "findings": [],
            "error": str(exc),
        }

    except Exception as exc:

        print(
            f"[ERROR] Unexpected error while scanning "
            f"account {target_account_id}: "
            f"{exc}"
        )

        return {
            "accountId": target_account_id,
            "success": False,
            "totalDashboardsScanned": 0,
            "totalCandidates": 0,
            "findings": [],
            "error": str(exc),
        }


# ============================================================
# 15. MULTI-ACCOUNT SCANNER
# ============================================================

def scan_all_accounts(
    account_ids: List[str],
) -> Dict[str, Any]:
    """
    Scan all configured AWS accounts.

    A failure in one account does not stop scanning of the
    remaining accounts.
    """

    base_sts = create_base_sts_client()

    all_findings: List[
        Dict[str, Any]
    ] = []

    account_results: List[
        Dict[str, Any]
    ] = []

    successful_accounts = 0

    failed_accounts = 0

    total_dashboards = 0

    total_candidates = 0

    # --------------------------------------------------------
    # Remove duplicate account IDs while preserving order.
    # --------------------------------------------------------

    unique_account_ids = list(
        dict.fromkeys(
            account_ids
        )
    )

    print(
        f"[INFO] Accounts configured: "
        f"{len(unique_account_ids)}"
    )

    # --------------------------------------------------------
    # Scan accounts sequentially.
    #
    # Sequential scanning is deliberately used here to avoid
    # excessive STS/API concurrency and account-level
    # throttling.
    # --------------------------------------------------------

    for account_id in unique_account_ids:

        result = scan_account(
            base_sts=base_sts,
            target_account_id=account_id,
        )

        account_results.append(
            result
        )

        if result.get(
            "success",
            False,
        ):

            successful_accounts += 1

            total_dashboards += result.get(
                "totalDashboardsScanned",
                0,
            )

            total_candidates += result.get(
                "totalCandidates",
                0,
            )

            all_findings.extend(
                result.get(
                    "findings",
                    [],
                )
            )

        else:

            failed_accounts += 1

    return {
        "policy": POLICY_NAME,

        "service": SERVICE_NAME,

        "resourceRegion": RESOURCE_REGION,

        "accountsRequested": len(
            unique_account_ids
        ),

        "accountsSuccessful": (
            successful_accounts
        ),

        "accountsFailed": (
            failed_accounts
        ),

        "totalDashboardsScanned": (
            total_dashboards
        ),

        "totalCandidates": (
            total_candidates
        ),

        "accountResults": account_results,

        "findings": all_findings,
    }


# ============================================================
# 16. ENTRY POINT
# ============================================================

if __name__ == "__main__":

    result = scan_all_accounts(
        account_ids=ACCOUNT_IDS
    )

    # --------------------------------------------------------
    # Print raw JSON result
    # --------------------------------------------------------

    print()
    print(
        "=" * 70
    )

    print(
        "[INFO] FINAL SCAN RESULT"
    )

    print(
        "=" * 70
    )

    print(
        json.dumps(
            result,
            indent=2,
            default=str,
        )
    )

    # --------------------------------------------------------
    # Export findings
    # --------------------------------------------------------

    export_to_excel(
        findings=result.get(
            "findings",
            [],
        ),
        filename=(
            "cloudwatch_dashboard_"
            "beyond_free_tier_idle.xlsx"
        ),
    )