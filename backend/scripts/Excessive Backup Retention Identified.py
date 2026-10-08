# ============================================================
# Excessive Backup Retention Identified
# AWS Backup + RDS
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

OUTPUT_FILE = "excessive_backup_retention_identified.xlsx"

AWS_CONFIG = Config(
    retries={
        "max_attempts": 10,
        "mode": "adaptive"
    }
)


# ============================================================
# 3. FinOps Policy Configuration
# ============================================================

POLICY_TITLE = "Excessive Backup Retention Identified"

SERVICE_NAME = "Backup"

RESOURCE_TYPE = "Backup Plan"

STATUS = "Pending for Review"

# Retention above this number of days is considered excessive.
OPTIMAL_RETENTION_DAYS = 30

# Reference backup storage price used only for the
# policy's heuristic cost/savings calculation.
#
# This is NOT used as actual AWS billing data.
BACKUP_STORAGE_PRICE_PER_GB_MONTH = 0.05


# ============================================================
# 4. Create AWS Clients
# ============================================================

def create_clients(region_name):
    backup = boto3.client(
        "backup",
        region_name=region_name,
        config=AWS_CONFIG
    )

    rds = boto3.client(
        "rds",
        region_name=region_name,
        config=AWS_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG
    )

    return backup, rds, sts


# ============================================================
# 5. Get Account ID
# ============================================================

def get_account_id(sts):
    return sts.get_caller_identity()["Account"]


# ============================================================
# 6. Fetch All Resources with Pagination
# ============================================================

def fetch_all_backup_plans(backup):
    """
    Fetch all AWS Backup plans in the configured region.
    """

    backup_plans = []

    paginator = backup.get_paginator("list_backup_plans")

    for page in paginator.paginate():
        backup_plans.extend(
            page.get("BackupPlansList", [])
        )

    return backup_plans


def fetch_backup_plan_details(backup, backup_plan_id):
    """
    Fetch complete backup plan configuration including
    backup rules and lifecycle/retention settings.
    """

    response = backup.get_backup_plan(
        BackupPlanId=backup_plan_id
    )

    return response.get("BackupPlan", {})


def fetch_all_backup_selections(backup, backup_plan_id):
    """
    Fetch all resource selections associated with
    a backup plan.
    """

    selections = []

    paginator = backup.get_paginator(
        "list_backup_selections"
    )

    try:
        for page in paginator.paginate(
            BackupPlanId=backup_plan_id
        ):
            selections.extend(
                page.get("BackupSelectionsList", [])
            )

    except Exception as exc:
        print(
            f"Warning: Unable to fetch selections "
            f"for backup plan {backup_plan_id}: {exc}"
        )

    return selections


def get_backup_selection_details(
    backup,
    backup_plan_id,
    selection_id
):
    """
    Fetch the detailed resource selection.
    """

    response = backup.get_backup_selection(
        BackupPlanId=backup_plan_id,
        SelectionId=selection_id
    )

    return response.get(
        "BackupSelection",
        {}
    )


# ============================================================
# 7. Fetch Additional AWS Data / Metrics
# ============================================================

def fetch_all_rds_instances(rds):
    """
    Fetch all RDS DB instances with pagination.
    """

    instances = []

    paginator = rds.get_paginator(
        "describe_db_instances"
    )

    for page in paginator.paginate():
        instances.extend(
            page.get("DBInstances", [])
        )

    return instances


def build_rds_lookup(rds_instances):
    """
    Build lookup maps for RDS resources.

    Supports:
        DB ARN
        DB identifier
    """

    lookup = {}

    for db in rds_instances:

        db_arn = db.get("DBInstanceArn")
        db_identifier = db.get("DBInstanceIdentifier")

        if db_arn:
            lookup[db_arn] = db

        if db_identifier:
            lookup[db_identifier] = db

    return lookup


def extract_rds_arns_from_selection(
    selection_details
):
    """
    Extract explicitly configured resource ARNs
    from an AWS Backup selection.

    AWS Backup selections can also use conditions/tags.
    Those dynamic selections cannot always be reduced to
    a static resource list from the selection object alone.
    """

    resources = selection_details.get(
        "Resources",
        []
    )

    rds_resources = []

    for resource in resources:

        if not resource:
            continue

        resource_lower = resource.lower()

        if ":rds:" in resource_lower:
            rds_resources.append(resource)

    return rds_resources


def calculate_backup_cost(
    storage_gb,
    retention_days
):
    """
    Heuristic backup storage cost.

    This is a policy estimate only.
    Actual AWS billing should come from CUR + Athena.
    """

    if storage_gb <= 0 or retention_days <= 0:
        return 0.0

    return (
        storage_gb
        * BACKUP_STORAGE_PRICE_PER_GB_MONTH
        * retention_days
        / 30
    )


def calculate_optimized_cost(storage_gb):
    """
    Estimated cost at the optimal retention period.
    """

    return calculate_backup_cost(
        storage_gb,
        OPTIMAL_RETENTION_DAYS
    )


def get_plan_rule_retention(rule):
    """
    Extract retention from an AWS Backup rule.

    DeleteAfterDays is the retention period when
    lifecycle is configured.
    """

    lifecycle = rule.get(
        "Lifecycle",
        {}
    )

    delete_after_days = lifecycle.get(
        "DeleteAfterDays"
    )

    if delete_after_days is None:
        return None

    try:
        return int(delete_after_days)
    except (TypeError, ValueError):
        return None


def get_plan_rules(backup_plan):
    """
    Return backup rules from the backup plan.
    """

    return backup_plan.get(
        "Rules",
        []
    )


# ============================================================
# 8. Evaluate FinOps Policy
# ============================================================

def evaluate_finops_policy(
    backup_plan,
    backup_plan_id,
    selection_details,
    rds_lookup
):
    """
    Evaluate excessive retention.

    Policy:
        retention > 30 days
    """

    findings = []

    plan_name = backup_plan.get(
        "BackupPlanName",
        backup_plan_id
    )

    rules = get_plan_rules(
        backup_plan
    )

    rds_arns = extract_rds_arns_from_selection(
        selection_details
    )

    # --------------------------------------------------------
    # If the selection explicitly identifies RDS resources,
    # evaluate each RDS resource.
    # --------------------------------------------------------

    for rule in rules:

        rule_name = rule.get(
            "RuleName",
            ""
        )

        retention_days = get_plan_rule_retention(
            rule
        )

        if retention_days is None:
            continue

        if retention_days <= OPTIMAL_RETENTION_DAYS:
            continue

        for rds_arn in rds_arns:

            rds_instance = rds_lookup.get(
                rds_arn
            )

            if not rds_instance:
                continue

            db_identifier = rds_instance.get(
                "DBInstanceIdentifier",
                ""
            )

            allocated_storage = rds_instance.get(
                "AllocatedStorage",
                0
            )

            try:
                allocated_storage = float(
                    allocated_storage
                )
            except (TypeError, ValueError):
                allocated_storage = 0.0

            current_cost = calculate_backup_cost(
                allocated_storage,
                retention_days
            )

            optimized_cost = calculate_optimized_cost(
                allocated_storage
            )

            estimated_savings = max(
                0.0,
                current_cost - optimized_cost
            )

            findings.append({
                "backupPlanId": backup_plan_id,
                "backupPlanName": plan_name,
                "ruleName": rule_name,
                "retentionDays": retention_days,
                "optimalRetentionDays":
                    OPTIMAL_RETENTION_DAYS,
                "resourceArn": rds_arn,
                "resourceName": db_identifier,
                "allocatedStorageGB":
                    allocated_storage,
                "currentEstimatedCost":
                    current_cost,
                "optimizedEstimatedCost":
                    optimized_cost,
                "estimatedMonthlySavings":
                    estimated_savings
            })

    return findings


# ============================================================
# 9. Build Standard Finding
# ============================================================

def build_standard_finding(
    finding,
    account_id
):
    """
    Convert policy finding into the fixed 30-column schema.
    """

    backup_plan_id = finding[
        "backupPlanId"
    ]

    backup_plan_name = finding[
        "backupPlanName"
    ]

    rule_name = finding[
        "ruleName"
    ]

    retention_days = finding[
        "retentionDays"
    ]

    optimal_retention_days = finding[
        "optimalRetentionDays"
    ]

    resource_arn = finding[
        "resourceArn"
    ]

    resource_name = finding[
        "resourceName"
    ]

    storage_gb = finding[
        "allocatedStorageGB"
    ]

    current_estimated_cost = finding[
        "currentEstimatedCost"
    ]

    optimized_estimated_cost = finding[
        "optimizedEstimatedCost"
    ]

    estimated_savings = finding[
        "estimatedMonthlySavings"
    ]

    description = (
        f"Backup Plan {backup_plan_id} "
        f"({backup_plan_name}) in Region {REGION} "
        f"protects RDS resource {resource_arn}; "
        f"Rule {rule_name}; "
        f"Retention {retention_days} Days; "
        f"Used/Allocated Size {storage_gb:.0f} GB; "
        f"Recommended Retention "
        f"{optimal_retention_days} Days; "
        f"Current Estimated Backup Cost "
        f"${current_estimated_cost:.2f}; "
        f"Optimized Estimated Cost "
        f"${optimized_estimated_cost:.2f}; "
        f"Estimated Monthly Savings "
        f"${estimated_savings:.2f}. "
        f"These cost values are heuristic estimates "
        f"and should be validated against CUR + Athena "
        f"before being treated as actual AWS costs."
    )

    return {
        "workItemType": "Task",
        "state": "To Do",
        "id": "",
        "title": POLICY_TITLE,
        "category": POLICY_TITLE,
        "owner": "",
        "assignedTo": "",
        "status": STATUS,
        "areaPath": "AWS Cost Optimization",
        "tags": "",
        "commentCount": 0,
        "accountId": account_id,
        "region": REGION,
        "resourceNameOrId": backup_plan_id,
        "resourceId": backup_plan_id,
        "resourceArn": "",
        "service": SERVICE_NAME,
        "type": RESOURCE_TYPE,
        "policy": POLICY_TITLE,
        "effortLevel": "",
        "message": (
            f"Backup Plan {backup_plan_id} has "
            f"{retention_days}-day retention for "
            f"RDS resource {resource_name}, "
            f"which exceeds the recommended "
            f"{optimal_retention_days}-day retention."
        ),
        "recommendation": (
            f"Review Backup Plan {backup_plan_id} "
            f"and reduce the retention period from "
            f"{retention_days} days to "
            f"{optimal_retention_days} days if the "
            f"longer retention is not required for "
            f"business, compliance, or recovery "
            f"requirements."
        ),
        "description": description,
        "currentDailyCost": "To be updated",
        "currentMonthlyCost": "To be updated",
        "estimatedMonthlySavings": "",
        "approvalComments": "",
        "reasonForRejection": "",
        "achievedSavingsMonthly": "",
        "month": ""
    }


# ============================================================
# 10. Scan Function
# ============================================================

def scan():
    """
    Main AWS Backup scanning workflow.
    """

    print("=" * 70)
    print("Starting Excessive Backup Retention Scan")
    print(f"Region: {REGION}")
    print("=" * 70)

    backup, rds, sts = create_clients(
        REGION
    )

    account_id = get_account_id(
        sts
    )

    print(f"Account ID: {account_id}")

    # --------------------------------------------------------
    # Fetch backup plans
    # --------------------------------------------------------

    backup_plans = fetch_all_backup_plans(
        backup
    )

    print(
        f"Backup Plans Found: "
        f"{len(backup_plans)}"
    )

    # --------------------------------------------------------
    # Fetch RDS resources
    # --------------------------------------------------------

    rds_instances = fetch_all_rds_instances(
        rds
    )

    print(
        f"RDS Instances Found: "
        f"{len(rds_instances)}"
    )

    rds_lookup = build_rds_lookup(
        rds_instances
    )

    findings = []

    # --------------------------------------------------------
    # Evaluate every backup plan
    # --------------------------------------------------------

    for plan_summary in backup_plans:

        backup_plan_id = plan_summary.get(
            "BackupPlanId"
        )

        if not backup_plan_id:
            continue

        try:

            backup_plan = fetch_backup_plan_details(
                backup,
                backup_plan_id
            )

        except Exception as exc:

            print(
                f"Warning: Unable to retrieve "
                f"backup plan {backup_plan_id}: {exc}"
            )

            continue

        selections = fetch_all_backup_selections(
            backup,
            backup_plan_id
        )

        for selection in selections:

            selection_id = selection.get(
                "SelectionId"
            )

            if not selection_id:
                continue

            try:

                selection_details = (
                    get_backup_selection_details(
                        backup,
                        backup_plan_id,
                        selection_id
                    )
                )

            except Exception as exc:

                print(
                    f"Warning: Unable to retrieve "
                    f"selection {selection_id} "
                    f"for plan {backup_plan_id}: {exc}"
                )

                continue

            plan_findings = evaluate_finops_policy(
                backup_plan,
                backup_plan_id,
                selection_details,
                rds_lookup
            )

            findings.extend(
                plan_findings
            )

    print(
        f"Excessive Retention Findings: "
        f"{len(findings)}"
    )

    # --------------------------------------------------------
    # Build standard findings
    # --------------------------------------------------------

    standard_findings = []

    for finding in findings:

        standard_finding = build_standard_finding(
            finding,
            account_id
        )

        standard_findings.append(
            standard_finding
        )

    return standard_findings


# ============================================================
# 11. Excel Export
# ============================================================

def export_to_excel(findings):
    """
    Export findings using the exact fixed 30-column schema.
    """

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

    df = pd.DataFrame(
        findings,
        columns=columns
    )

    df.to_excel(
        OUTPUT_FILE,
        index=False
    )

    print("=" * 70)
    print(f"Excel file created: {OUTPUT_FILE}")
    print(f"Total findings: {len(df)}")
    print("=" * 70)


# ============================================================
# 12. Main
# ============================================================

if __name__ == "__main__":

    start_time = datetime.now(
        timezone.utc
    )

    try:

        findings = scan()

        export_to_excel(
            findings
        )

        end_time = datetime.now(
            timezone.utc
        )

        duration = (
            end_time - start_time
        ).total_seconds()

        print(
            f"Scan completed successfully "
            f"in {duration:.2f} seconds."
        )

    except Exception as exc:

        print(
            f"Scan failed: {exc}"
        )

        raise