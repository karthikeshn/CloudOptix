
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

import pandas as pd
import json


# ============================================================
# CONFIGURATION
# ============================================================

POLICY_NAME = (
    "backup-plan-cross-region-copy"
)

CATEGORY = (
    "Backup Plan with Cross-Region Copies"
)

SERVICE_NAME = "Backup"

EFFORT_LEVEL = "Medium"


# ============================================================
# AWS CLIENT CONFIGURATION
# ============================================================

AWS_CONFIG = Config(
    retries={
        "mode": "adaptive",
        "max_attempts": 10,
    }
)


# ============================================================
# CREATE AWS CLIENTS
# ============================================================

def create_clients(
    region_name: str,
):

    backup = boto3.client(
        "backup",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    sts = boto3.client(
        "sts",
        config=AWS_CONFIG,
    )

    return backup, sts


# ============================================================
# ACCOUNT ID
# ============================================================

def get_account_id(
    sts,
) -> str:

    return sts.get_caller_identity()["Account"]


# ============================================================
# FETCH ALL BACKUP PLANS
# ============================================================

def fetch_all_backup_plans(
    backup,
) -> List[Dict[str, Any]]:
    """
    Automatically fetch ALL AWS Backup plans
    in the supplied region.

    Pagination is handled using boto3 paginator.
    """

    backup_plans = []

    paginator = backup.get_paginator(
        "list_backup_plans"
    )

    for page in paginator.paginate():

        page_plans = page.get(
            "BackupPlansList",
            []
        )

        backup_plans.extend(
            page_plans
        )

    return backup_plans


# ============================================================
# FETCH BACKUP PLAN DETAILS
# ============================================================

def fetch_backup_plan_details(
    backup,
    backup_plan_id: str,
) -> Dict[str, Any]:
    """
    Fetch complete Backup Plan configuration.
    """

    response = backup.get_backup_plan(
        BackupPlanId=backup_plan_id
    )

    return response.get(
        "BackupPlan",
        {}
    )


# ============================================================
# FETCH ALL BACKUP RULES
# ============================================================

def fetch_backup_rules(
    backup,
    backup_plan_id: str,
) -> List[Dict[str, Any]]:
    """
    Fetch all rules configured inside a Backup Plan.

    Pagination is handled using boto3 paginator.
    """

    rules = []

    paginator = backup.get_paginator(
        "list_backup_plan_templates"
    )

    # --------------------------------------------------------
    # Backup rules are normally returned by get_backup_plan()
    # under BackupPlan.Rules.
    #
    # Therefore we don't actually need this paginator.
    # This function is retained as a separate abstraction so
    # the scanner has a clean structure.
    # --------------------------------------------------------

    del paginator

    try:

        response = backup.get_backup_plan(
            BackupPlanId=backup_plan_id
        )

        backup_plan = response.get(
            "BackupPlan",
            {}
        )

        rules = backup_plan.get(
            "Rules",
            []
        )

    except ClientError as error:

        print(
            f"Could not fetch rules for "
            f"backup plan {backup_plan_id}: "
            f"{error}"
        )

    return rules


# ============================================================
# CHECK CROSS REGION
# ============================================================

def find_cross_region_copy_actions(
    rules: List[Dict[str, Any]],
    source_region: str,
) -> List[Dict[str, Any]]:
    """
    Inspect all Backup Plan rules and find CopyActions.

    A CopyAction whose destination vault belongs to another
    region is treated as a cross-region copy.

    Example:

        Source:
            eu-west-1

        Destination:
            eu-west-2

        => Cross-region copy
    """

    cross_region_copies = []

    for rule in rules:

        rule_id = rule.get(
            "RuleId"
        )

        rule_name = rule.get(
            "RuleName"
        )

        copy_actions = rule.get(
            "CopyActions",
            []
        )

        for copy_action in copy_actions:

            destination_vault_arn = (
                copy_action.get(
                    "DestinationBackupVaultArn"
                )
            )

            if not destination_vault_arn:
                continue

            destination_region = (
                extract_region_from_arn(
                    destination_vault_arn
                )
            )

            # ------------------------------------------------
            # If region cannot be extracted, don't assume it
            # is cross-region.
            # ------------------------------------------------

            if not destination_region:

                continue

            is_cross_region = (
                destination_region
                != source_region
            )

            if is_cross_region:

                cross_region_copies.append({

                    "ruleId": rule_id,

                    "ruleName": rule_name,

                    "destinationBackupVaultArn":
                        destination_vault_arn,

                    "destinationRegion":
                        destination_region,

                    "lifecycle":
                        copy_action.get(
                            "Lifecycle",
                            {}
                        ),

                    "deleteAfterDays":
                        extract_delete_after_days(
                            copy_action
                        ),

                    "coldStorageAfterDays":
                        extract_cold_storage_after_days(
                            copy_action
                        ),
                })

    return cross_region_copies


# ============================================================
# EXTRACT REGION FROM ARN
# ============================================================

def extract_region_from_arn(
    arn: str,
) -> str | None:
    """
    Extract AWS region from an ARN.

    Example:

        arn:aws:backup:eu-west-2:123456789012:
        backup-vault:my-vault

    returns:

        eu-west-2
    """

    try:

        parts = arn.split(":")

        if len(parts) >= 4:

            return parts[3]

    except Exception:

        pass

    return None


# ============================================================
# EXTRACT DELETE AFTER DAYS
# ============================================================

def extract_delete_after_days(
    copy_action: Dict[str, Any],
) -> int | None:

    lifecycle = copy_action.get(
        "Lifecycle",
        {}
    )

    delete_after_days = (
        lifecycle.get(
            "DeleteAfterDays"
        )
    )

    return delete_after_days


# ============================================================
# EXTRACT COLD STORAGE DAYS
# ============================================================

def extract_cold_storage_after_days(
    copy_action: Dict[str, Any],
) -> int | None:

    lifecycle = copy_action.get(
        "Lifecycle",
        {}
    )

    cold_storage_after_days = (
        lifecycle.get(
            "MoveToColdStorageAfterDays"
        )
    )

    return cold_storage_after_days


# ============================================================
# FETCH BACKUP PLAN TAGS
# ============================================================

def fetch_backup_plan_tags(
    backup,
    backup_plan_arn: str,
) -> Dict[str, str]:
    """
    Fetch tags attached to the Backup Plan.
    """

    try:

        response = backup.list_tags(
            ResourceArn=backup_plan_arn
        )

        tags = response.get(
            "Tags",
            {}
        )

        return tags

    except ClientError as error:

        print(
            f"Could not fetch tags for "
            f"{backup_plan_arn}: {error}"
        )

        return {}


# ============================================================
# COST PLACEHOLDER
# ============================================================

def get_resource_cost(
    account_id: str,
    region_name: str,
    resource_arn: str,
) -> Dict[str, Any]:
    """
    Cost values should come from your centralized
    CUR + Athena cost layer.

    Do NOT hardcode AWS Backup prices here.

    Expected future values:

        currentDailyCost
        currentMonthlyCost
        estimatedMonthlySavings
    """

    return {

        "currentDailyCost": None,

        "currentMonthlyCost": None,

        "estimatedMonthlySavings": None,
    }


# ============================================================
# BUILD RECOMMENDATION
# ============================================================

def build_recommendation(
    plan_name: str,
    source_region: str,
    destination_regions: List[str],
) -> str:

    destination_text = ", ".join(
        sorted(
            set(
                destination_regions
            )
        )
    )

    return (

        f"AWS Backup plan '{plan_name}' "
        f"in {source_region} has cross-region "
        f"copy actions to {destination_text}. "

        f"Review whether these cross-region copies "
        f"are required for disaster recovery, "
        f"business continuity, or compliance. "

        f"If they are not required, consider "
        f"disabling unnecessary cross-region copies "
        f"to reduce backup storage and related "
        f"data transfer costs."
    )


# ============================================================
# BUILD FINOPS FINDING
# ============================================================

def build_backup_finding(
    backup_plan: Dict[str, Any],
    backup_plan_details: Dict[str, Any],
    account_id: str,
    region_name: str,
    tags: Dict[str, str],
    cross_region_copies: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build standardized FinOps finding.
    """

    plan_id = (
        backup_plan.get(
            "BackupPlanId"
        )
    )

    plan_arn = (
        backup_plan.get(
            "BackupPlanArn"
        )
    )

    plan_name = (
        backup_plan.get(
            "BackupPlanName"
        )
        or backup_plan_details.get(
            "BackupPlanName"
        )
        or plan_id
    )

    creation_date = (
        backup_plan.get(
            "CreationDate"
        )
    )

    last_execution_date = (
        backup_plan.get(
            "LastExecutionDate"
        )
    )

    destination_regions = [

        copy[
            "destinationRegion"
        ]

        for copy in cross_region_copies

        if copy.get(
            "destinationRegion"
        )
    ]

    destination_regions = sorted(
        set(
            destination_regions
        )
    )

    rule_ids = [

        copy.get(
            "ruleId"
        )

        for copy in cross_region_copies
    ]

    rule_names = [

        copy.get(
            "ruleName"
        )

        for copy in cross_region_copies
    ]

    copy_vault_arns = [

        copy.get(
            "destinationBackupVaultArn"
        )

        for copy in cross_region_copies
    ]

    # --------------------------------------------------------
    # Cost
    # --------------------------------------------------------

    cost = get_resource_cost(
        account_id=account_id,

        region_name=region_name,

        resource_arn=plan_arn,
    )

    # --------------------------------------------------------
    # Recommendation
    # --------------------------------------------------------

    recommendation = (
        build_recommendation(
            plan_name=plan_name,

            source_region=region_name,

            destination_regions=(
                destination_regions
            ),
        )
    )

    # --------------------------------------------------------
    # Message
    # --------------------------------------------------------

    message = (

        f"AWS Backup plan '{plan_name}' "
        f"in {region_name} has "
        f"{len(cross_region_copies)} "
        f"cross-region copy action(s). "

        f"Destination region(s): "
        f"{', '.join(destination_regions)}. "

        f"Review necessity based on DR, "
        f"business continuity and compliance "
        f"requirements."
    )

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    description = (

        f"accountId: {account_id} | "

        f"region: {region_name} | "

        f"resourceId: {plan_id} | "

        f"arn: {plan_arn} | "

        f"Type: Cross-Region Backup Copy | "

        f"policy: {POLICY_NAME} | "

        f"message: {message} | "

        f"effortLevel: {EFFORT_LEVEL} | "

        f"backupPlanName: {plan_name} | "

        f"crossRegionCopyCount: "
        f"{len(cross_region_copies)} | "

        f"destinationRegions: "
        f"{', '.join(destination_regions)}"
    )

    # --------------------------------------------------------
    # Return standardized finding
    # --------------------------------------------------------

    return {

        # ====================================================
        # WORKFLOW
        # ====================================================

        "workItemType": "Task",

        "state": "To Do",

        "title": (
            "Backup Plan with Cross-Region Copies"
        ),

        "category": CATEGORY,

        "owner": "",

        "assignedTo": "",

        "status": "Pending for Review",

        "areaPath": (
            "AWS Cost Optimization"
        ),

        "tags": tags,

        "commentCount": 0,

        # ====================================================
        # AWS IDENTITY
        # ====================================================

        "accountId": account_id,

        "region": region_name,

        "resourceNameOrId": plan_id,

        "resourceId": plan_id,

        "resourceArn": plan_arn,

        "service": SERVICE_NAME,

        # ====================================================
        # BACKUP PLAN
        # ====================================================

        "backupPlanId": plan_id,

        "backupPlanName": plan_name,

        "creationDate": (
            creation_date.isoformat()
            if creation_date
            else None
        ),

        "lastExecutionDate": (
            last_execution_date.isoformat()
            if last_execution_date
            else None
        ),

        # ====================================================
        # CROSS REGION COPY
        # ====================================================

        "hasCrossRegionCopy": True,

        "crossRegionCopyCount": (
            len(cross_region_copies)
        ),

        "destinationRegions": (
            destination_regions
        ),

        "ruleIds": rule_ids,

        "ruleNames": rule_names,

        "destinationBackupVaultArns":
            copy_vault_arns,

        "copyActions":
            cross_region_copies,

        # ====================================================
        # FINOPS
        # ====================================================

        "type": (
            "Cross-Region Backup Copy"
        ),

        "policy": POLICY_NAME,

        "effortLevel": EFFORT_LEVEL,

        "recommendation": recommendation,

        "message": message,

        "description": description,

        # ====================================================
        # COST
        # ====================================================

        "currentDailyCost": (
            cost[
                "currentDailyCost"
            ]
        ),

        "currentMonthlyCost": (
            cost[
                "currentMonthlyCost"
            ]
        ),

        "estimatedMonthlySavings": (
            cost[
                "estimatedMonthlySavings"
            ]
        ),

        # ====================================================
        # HUMAN WORKFLOW
        # ====================================================

        "approvalComments": "",

        "reasonForRejection": "",

        "achievedSavingsMonthly": "",

        "month": "",
    }


# ============================================================
# SCAN BACKUP PLANS
# ============================================================

def scan_backup_plans(
    region_name: str,
) -> Dict[str, Any]:
    """
    Scan all AWS Backup plans in a region.
    """

    backup, sts = create_clients(
        region_name
    )

    account_id = get_account_id(
        sts
    )

    # --------------------------------------------------------
    # Automatically discover all backup plans
    # --------------------------------------------------------

    backup_plans = (
        fetch_all_backup_plans(
            backup
        )
    )

    findings = []

    inventory = []

    # --------------------------------------------------------
    # Process each backup plan
    # --------------------------------------------------------

    for backup_plan in backup_plans:

        plan_id = (
            backup_plan.get(
                "BackupPlanId"
            )
        )

        plan_name = (
            backup_plan.get(
                "BackupPlanName"
            )
        )

        plan_arn = (
            backup_plan.get(
                "BackupPlanArn"
            )
        )

        print(
            f"\nProcessing Backup Plan: "
            f"{plan_name}"
        )

        print(
            f"Plan ID: {plan_id}"
        )

        # ----------------------------------------------------
        # Fetch detailed configuration
        # ----------------------------------------------------

        try:

            plan_details = (
                fetch_backup_plan_details(
                    backup,
                    plan_id,
                )
            )

        except ClientError as error:

            print(
                f"Could not fetch backup plan "
                f"{plan_id}: {error}"
            )

            continue

        # ----------------------------------------------------
        # Fetch tags
        # ----------------------------------------------------

        tags = fetch_backup_plan_tags(
            backup,
            plan_arn,
        )

        # ----------------------------------------------------
        # Rules
        # ----------------------------------------------------

        rules = plan_details.get(
            "Rules",
            []
        )

        # ----------------------------------------------------
        # Find cross-region copies
        # ----------------------------------------------------

        cross_region_copies = (
            find_cross_region_copy_actions(
                rules=rules,

                source_region=region_name,
            )
        )

        # ----------------------------------------------------
        # Inventory
        # ----------------------------------------------------

        inventory.append({

            "accountId": account_id,

            "region": region_name,

            "backupPlanId": plan_id,

            "backupPlanName": plan_name,

            "backupPlanArn": plan_arn,

            "ruleCount": len(
                rules
            ),

            "hasCrossRegionCopy": bool(
                cross_region_copies
            ),

            "crossRegionCopyCount": len(
                cross_region_copies
            ),

            "destinationRegions": (
                [
                    copy[
                        "destinationRegion"
                    ]

                    for copy
                    in cross_region_copies
                ]
            ),

            "tags": tags,
        })

        # ----------------------------------------------------
        # Policy
        # ----------------------------------------------------

        if cross_region_copies:

            finding = (
                build_backup_finding(

                    backup_plan=backup_plan,

                    backup_plan_details=(
                        plan_details
                    ),

                    account_id=account_id,

                    region_name=region_name,

                    tags=tags,

                    cross_region_copies=(
                        cross_region_copies
                    ),
                )
            )

            findings.append(
                finding
            )

    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    return {

        "accountId": account_id,

        "region": region_name,

        "totalBackupPlansScanned": (
            len(backup_plans)
        ),

        "totalCrossRegionCopyPlans": (
            len(findings)
        ),

        "findings": findings,

        "backupPlanInventory": inventory,
    }


# ============================================================
# EXPORT TO EXCEL
# ============================================================

def export_to_excel(
    findings: List[Dict[str, Any]],
    filename: str,
):
    STANDARD_COLUMNS = [
        "workItemType", "state", "id", "title", "category", "owner",
        "assignedTo", "status", "areaPath", "tags", "commentCount",
        "accountId", "region", "resourceNameOrId", "resourceId",
        "resourceArn", "service", "type", "policy", "effortLevel",
        "message", "recommendation", "description", "currentDailyCost",
        "currentMonthlyCost", "estimatedMonthlySavings", "approvalComments",
        "reasonForRejection", "achievedSavingsMonthly", "month"
    ]

    flat_findings = []
    
    # Handle single dictionary (like Snapshot.py) or list of dictionaries
    if isinstance(findings, dict):
        findings = [findings]

    for finding in findings:
        flat_finding = {}
        extra_attributes = []
        
        # 1. Separate standard columns from extra attributes
        for key, value in finding.items():
            if isinstance(value, (dict, list)):
                import json
                str_val = json.dumps(value, default=str)
            else:
                str_val = value

            if key in STANDARD_COLUMNS:
                flat_finding[key] = str_val
            else:
                # Capture extra attributes
                extra_attributes.append(f"{key}: {str_val}")
                
        # 2. Build final standard row
        standard_row = {col: "" for col in STANDARD_COLUMNS}
        
        # Populate standard values
        for k, v in flat_finding.items():
            standard_row[k] = v
            
        # 3. Append extra attributes to description
        existing_desc = standard_row.get("description", "")
        if existing_desc is None:
            existing_desc = ""
            
        if extra_attributes:
            extra_str = " | ".join(extra_attributes)
            if existing_desc:
                standard_row["description"] = f"{existing_desc} | {extra_str}"
            else:
                standard_row["description"] = extra_str
                
        flat_findings.append(standard_row)

    import pandas as pd
    df = pd.DataFrame(flat_findings, columns=STANDARD_COLUMNS)

    df.to_excel(
        filename,
        index=False
    )

    print(f"\\nExcel report created:\\n{filename}")


if __name__ == "__main__":

    # --------------------------------------------------------
    # ONLY REGION IS SUPPLIED.
    #
    # Backup Plan IDs are discovered automatically.
    # --------------------------------------------------------

    import os
    region = os.environ.get("AWS_REGION", "eu-west-1")

    print(
        "\n=========================================="
    )

    print(
        "AWS BACKUP CROSS-REGION COPY SCANNER"
    )

    print(
        "=========================================="
    )

    print(
        f"Region: {region}"
    )

    print(
        f"Policy: {POLICY_NAME}"
    )

    print(
        "=========================================="
    )

    # --------------------------------------------------------
    # Scan
    # --------------------------------------------------------

    result = scan_backup_plans(
        region
    )

    # --------------------------------------------------------
    # Print JSON
    # --------------------------------------------------------

    print(
        json.dumps(
            result,
            indent=2,
            default=str
        )
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print(
        "\n=========================================="
    )

    print(
        "SUMMARY"
    )

    print(
        "=========================================="
    )

    print(
        "Account ID:",
        result[
            "accountId"
        ]
    )

    print(
        "Region:",
        result[
            "region"
        ]
    )

    print(
        "Backup Plans scanned:",
        result[
            "totalBackupPlansScanned"
        ]
    )

    print(
        "Plans with cross-region copies:",
        result[
            "totalCrossRegionCopyPlans"
        ]
    )

    print(
        "=========================================="
    )

    # --------------------------------------------------------
    # Findings
    # --------------------------------------------------------

    findings = result.get(
        "findings",
        []
    )

    if not findings:

        print(
            "\nNo Backup Plans with "
            "cross-region copy actions found."
        )

    # --------------------------------------------------------
    # Export
    # --------------------------------------------------------

    excel_file = (
        "backup_cross_region_copy_report.xlsx"
    )

    export_to_excel(
        findings=findings,

        filename=excel_file,
    )

    print(
        "\nCompleted."
    )

