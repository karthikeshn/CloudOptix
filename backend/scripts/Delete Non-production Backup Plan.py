# ============================================================
# AWS FinOps Policy
# Policy: Delete Non-production Backup Plan
# ============================================================

# ============================================================
# 1. Imports
# ============================================================

import boto3
import pandas as pd

from datetime import datetime, timezone
from botocore.config import Config


# ============================================================
# 2. AWS Configuration
# ============================================================

REGION = "us-east-1"

OUTPUT_FILE = "delete_non_production_backup_plan.xlsx"

AWS_CONFIG = Config(
    retries={
        "max_attempts": 10,
        "mode": "adaptive"
    }
)


# ============================================================
# 3. FinOps Policy Configuration
# ============================================================

POLICY_TITLE = "Delete Non-production Backup Plan"
CATEGORY = "Delete Non-production Backup Plan"
SERVICE = "AWS Backup"

NON_PRODUCTION_KEYWORDS = [
    "dev",
    "development",
    "test",
    "testing",
    "qa",
    "uat",
    "stage",
    "staging",
    "nonprod",
    "non-prod",
    "non-production"
]

# Backup plans that should generally be reviewed before deletion.
# The script only identifies candidates; it does NOT delete them.
PROTECTED_KEYWORDS = [
    "prod",
    "production",
    "critical",
    "dr",
    "disaster-recovery"
]


# ============================================================
# 4. Create AWS Clients
# ============================================================

def create_clients(region_name):
    """
    Create AWS service clients.
    """

    backup = boto3.client(
        "backup",
        region_name=region_name,
        config=AWS_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG
    )

    return backup, sts


# ============================================================
# 5. Get Account ID
# ============================================================

def get_account_id(sts):
    """
    Get AWS Account ID.
    """

    return sts.get_caller_identity()["Account"]


# ============================================================
# 6. Fetch All Resources with Pagination
# ============================================================

def fetch_all_backup_plans(backup):
    """
    Fetch all AWS Backup plans in the region.

    list_backup_plans() is paginated using NextToken.
    """

    backup_plans = []

    next_token = None

    while True:

        params = {}

        if next_token:
            params["NextToken"] = next_token

        response = backup.list_backup_plans(**params)

        backup_plans.extend(
            response.get("BackupPlansList", [])
        )

        next_token = response.get("NextToken")

        if not next_token:
            break

    return backup_plans


def fetch_backup_plan_details(backup, backup_plan_id):
    """
    Fetch detailed information for a backup plan.
    """

    try:

        response = backup.get_backup_plan(
            BackupPlanId=backup_plan_id
        )

        return response.get("BackupPlan", {})

    except Exception as e:

        print(
            f"Unable to fetch backup plan "
            f"{backup_plan_id}: {e}"
        )

        return {}


def fetch_backup_plan_resource_assignments(
    backup,
    backup_plan_id
):
    """
    Fetch resources assigned to the backup plan.

    This helps determine whether the backup plan is actually
    protecting resources.
    """

    selections = []

    next_token = None

    while True:

        params = {
            "BackupPlanId": backup_plan_id
        }

        if next_token:
            params["NextToken"] = next_token

        response = backup.list_backup_selections(
            **params
        )

        selections.extend(
            response.get(
                "BackupSelectionsList",
                []
            )
        )

        next_token = response.get("NextToken")

        if not next_token:
            break

    return selections


def fetch_backup_selection_details(
    backup,
    backup_plan_id,
    selection_id
):
    """
    Fetch details of a backup selection.
    """

    try:

        response = backup.get_backup_selection(
            BackupPlanId=backup_plan_id,
            SelectionId=selection_id
        )

        return response.get(
            "BackupSelection",
            {}
        )

    except Exception as e:

        print(
            f"Unable to fetch backup selection "
            f"{selection_id}: {e}"
        )

        return {}


# ============================================================
# 7. Fetch Additional AWS Data / Metrics as Required
# ============================================================

def get_backup_plan_protected_resources(
    backup,
    backup_plan_id
):
    """
    Collect resources referenced by all selections
    associated with the backup plan.

    Note:
    AWS Backup selections can use explicit resource ARNs
    and/or tag-based conditions.
    """

    protected_resources = []

    selections = fetch_backup_plan_resource_assignments(
        backup,
        backup_plan_id
    )

    for selection in selections:

        selection_id = selection.get(
            "SelectionId"
        )

        if not selection_id:
            continue

        selection_details = (
            fetch_backup_selection_details(
                backup,
                backup_plan_id,
                selection_id
            )
        )

        resources = selection_details.get(
            "Resources",
            []
        )

        protected_resources.extend(
            resources
        )

    return protected_resources


def get_backup_plan_resource_types(
    protected_resources
):
    """
    Determine service/resource types from resource ARNs.
    """

    resource_types = set()

    for resource in protected_resources:

        if not isinstance(resource, str):
            continue

        resource_lower = resource.lower()

        if ":dynamodb:" in resource_lower:
            resource_types.add("DynamoDB")

        elif ":s3:" in resource_lower:
            resource_types.add("S3")

        elif ":ec2:" in resource_lower:
            resource_types.add("EC2")

        elif ":rds:" in resource_lower:
            resource_types.add("RDS")

        elif ":efs:" in resource_lower:
            resource_types.add("EFS")

        elif ":fsx:" in resource_lower:
            resource_types.add("FSx")

        elif ":storagegateway:" in resource_lower:
            resource_types.add("Storage Gateway")

        else:
            resource_types.add("Unknown")

    return sorted(resource_types)


# ============================================================
# 8. Evaluate FinOps Policy
# ============================================================

def is_non_production_backup_plan(
    backup_plan_name
):
    """
    Determine whether the backup plan appears to be
    non-production based on its name.

    This is intentionally conservative.
    """

    if not backup_plan_name:
        return False

    name = backup_plan_name.lower()

    has_non_prod_keyword = any(
        keyword in name
        for keyword in NON_PRODUCTION_KEYWORDS
    )

    has_protected_keyword = any(
        keyword in name
        for keyword in PROTECTED_KEYWORDS
    )

    if has_non_prod_keyword and not has_protected_keyword:
        return True

    return False


def evaluate_backup_plan(
    backup,
    backup_plan,
    account_id,
    region
):
    """
    Evaluate one backup plan against the policy.
    """

    backup_plan_id = backup_plan.get(
        "BackupPlanId"
    )

    backup_plan_arn = backup_plan.get(
        "BackupPlanArn"
    )

    backup_plan_name = backup_plan.get(
        "BackupPlanName"
    )

    creation_date = backup_plan.get(
        "CreationDate"
    )

    if not is_non_production_backup_plan(
        backup_plan_name
    ):
        return None

    protected_resources = (
        get_backup_plan_protected_resources(
            backup,
            backup_plan_id
        )
    )

    resource_types = (
        get_backup_plan_resource_types(
            protected_resources
        )
    )

    return {
        "account_id": account_id,
        "region": region,
        "backup_plan_id": backup_plan_id,
        "backup_plan_arn": backup_plan_arn,
        "backup_plan_name": backup_plan_name,
        "creation_date": creation_date,
        "protected_resource_count": len(
            protected_resources
        ),
        "protected_resources": protected_resources,
        "resource_types": resource_types
    }


# ============================================================
# 9. Build FinOps Findings
# ============================================================

def build_finding(
    evaluation
):
    """
    Convert an evaluated backup plan into a FinOps finding.
    """

    account_id = evaluation["account_id"]
    region = evaluation["region"]

    backup_plan_name = evaluation[
        "backup_plan_name"
    ]

    backup_plan_id = evaluation[
        "backup_plan_id"
    ]

    backup_plan_arn = evaluation[
        "backup_plan_arn"
    ]

    creation_date = evaluation[
        "creation_date"
    ]

    protected_resource_count = evaluation[
        "protected_resource_count"
    ]

    resource_types = evaluation[
        "resource_types"
    ]

    protected_resources = evaluation[
        "protected_resources"
    ]

    resource_types_text = (
        ", ".join(resource_types)
        if resource_types
        else "No explicit resource type identified"
    )

    protected_resources_text = (
        ", ".join(protected_resources[:20])
        if protected_resources
        else "No explicitly assigned resources"
    )

    description = (
        "Non-production AWS Backup plan identified for review. "
        f"Backup Plan: {backup_plan_name}. "
        f"Backup Plan ID: {backup_plan_id}. "
        f"Protected resource count identified from backup "
        f"selections: {protected_resource_count}. "
        f"Resource types: {resource_types_text}. "
        f"Creation date: {creation_date}. "
        f"Resources: {protected_resources_text}."
    )

    return {
        "workItemType": "Task",
        "state": "To Do",
        "id": "",
        "title": POLICY_TITLE,
        "category": CATEGORY,
        "owner": "",
        "assignedTo": "",
        "status": "Pending for Review",
        "areaPath": "AWS Cost Optimization",
        "tags": "",
        "commentCount": 0,

        "accountId": account_id,
        "region": region,
        "resourceNameOrId": backup_plan_name,
        "resourceId": backup_plan_id,
        "resourceArn": backup_plan_arn,
        "service": SERVICE,

        "type": "Backup Plan",
        "policy": POLICY_TITLE,
        "effortLevel": "Medium",
        "message": f"Non-production backup plan {backup_plan_name} identified for review.",
        "recommendation": "Review whether the backup plan is required before deletion.",
        "description": description,

        "currentDailyCost": None,
        "currentMonthlyCost": None,
        "estimatedMonthlySavings": None,
        "approvalComments": "",
        "reasonForRejection": "",
        "achievedSavingsMonthly": None,
        "month": ""
    }


# ============================================================
# 10. Main Execution
# ============================================================

def main():

    scan_start_time = datetime.now(
        timezone.utc
    )

    print("=" * 70)
    print("AWS FinOps Policy Scan")
    print(f"Policy : {POLICY_TITLE}")
    print(f"Region : {REGION}")
    print("=" * 70)

    # --------------------------------------------------------
    # Create clients
    # --------------------------------------------------------

    backup, sts = create_clients(
        REGION
    )

    # --------------------------------------------------------
    # Account ID
    # --------------------------------------------------------

    account_id = get_account_id(sts)

    print(
        f"Account ID : {account_id}"
    )

    # --------------------------------------------------------
    # Fetch Backup Plans
    # --------------------------------------------------------

    print(
        "Fetching AWS Backup plans..."
    )

    backup_plans = fetch_all_backup_plans(
        backup
    )

    print(
        f"Backup plans scanned : "
        f"{len(backup_plans)}"
    )

    # --------------------------------------------------------
    # Evaluate Backup Plans
    # --------------------------------------------------------

    findings = []

    for backup_plan in backup_plans:

        evaluation = evaluate_backup_plan(
            backup,
            backup_plan,
            account_id,
            REGION
        )

        if evaluation:

            finding = build_finding(
                evaluation
            )

            findings.append(
                finding
            )

    # --------------------------------------------------------
    # Create DataFrame
    # --------------------------------------------------------

    columns = [
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
        "month"
    ]

    dataframe = pd.DataFrame(
        findings,
        columns=columns
    )

    # --------------------------------------------------------
    # Export Excel
    # --------------------------------------------------------

    dataframe.to_excel(
        OUTPUT_FILE,
        index=False
    )

    scan_end_time = datetime.now(
        timezone.utc
    )

    scan_duration = (
        scan_end_time - scan_start_time
    ).total_seconds()

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("SCAN SUMMARY")
    print("=" * 70)

    print(
        f"Account ID              : {account_id}"
    )

    print(
        f"Region                  : {REGION}"
    )

    print(
        f"Backup Plans Scanned    : "
        f"{len(backup_plans)}"
    )

    print(
        f"Non-Production Findings : "
        f"{len(findings)}"
    )

    print(
        f"Scan Duration           : "
        f"{scan_duration:.2f} seconds"
    )

    print(
        f"Excel Output            : "
        f"{OUTPUT_FILE}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()