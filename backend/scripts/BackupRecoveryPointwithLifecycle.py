

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

# Recovery points older than this threshold are considered
# candidates when they do not have a lifecycle policy.

RECOVERY_POINT_AGE_THRESHOLD_DAYS = 0


# ============================================================
# FINOPS POLICY
# ============================================================

POLICY_NAME = (
    "backup-recovery-point-without-lifecycle"
)

CATEGORY = (
    "Backup Recovery Point with Lifecycle"
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
# GET ACCOUNT ID
# ============================================================

def get_account_id(
    sts,
) -> str:

    return sts.get_caller_identity()["Account"]


# ============================================================
# FETCH ALL BACKUP VAULTS
# ============================================================

def fetch_all_backup_vaults(
    backup,
) -> List[Dict[str, Any]]:
    """
    Fetch all AWS Backup vaults in the region.

    Pagination is handled automatically.
    """

    vaults = []

    paginator = backup.get_paginator(
        "list_backup_vaults"
    )

    for page in paginator.paginate():

        vaults.extend(
            page.get(
                "BackupVaultList",
                []
            )
        )

    return vaults


# ============================================================
# FETCH ALL RECOVERY POINTS
# ============================================================

def fetch_all_recovery_points(
    backup,
    backup_vault_name: str,
) -> List[Dict[str, Any]]:
    """
    Fetch all recovery points from a Backup Vault.

    Pagination is handled automatically.
    """

    recovery_points = []

    paginator = backup.get_paginator(
        "list_recovery_points_by_backup_vault"
    )

    for page in paginator.paginate(
        BackupVaultName=backup_vault_name
    ):

        recovery_points.extend(
            page.get(
                "RecoveryPoints",
                []
            )
        )

    return recovery_points


# ============================================================
# CALCULATE AGE
# ============================================================

def calculate_age_days(
    creation_date: datetime | None,
) -> float | None:
    """
    Calculate recovery point age in days.
    """

    if creation_date is None:
        return None

    if creation_date.tzinfo is None:

        creation_date = (
            creation_date.replace(
                tzinfo=timezone.utc
            )
        )

    now = datetime.now(
        timezone.utc
    )

    age_days = (
        now - creation_date
    ).total_seconds() / 86400

    # Prevent invalid future dates from creating
    # negative ages.

    if age_days < 0:
        return 0.0

    return round(
        age_days,
        2,
    )


# ============================================================
# CHECK RECOVERY POINT AGE
# ============================================================

def is_old_recovery_point(
    age_days: float | None,
) -> bool:

    if age_days is None:
        return False

    return (
        age_days
        >= RECOVERY_POINT_AGE_THRESHOLD_DAYS
    )


# ============================================================
# CHECK LIFECYCLE POLICY
# ============================================================

def has_lifecycle_policy(
    recovery_point: Dict[str, Any],
) -> bool:
    """
    AWS Backup recovery point lifecycle contains
    lifecycle configuration when configured.

    Typical fields:

        MoveToColdStorageAfterDays
        DeleteAfterDays
    """

    lifecycle = recovery_point.get(
        "Lifecycle"
    )

    if not lifecycle:
        return False

    move_to_cold = lifecycle.get(
        "MoveToColdStorageAfterDays"
    )

    delete_after = lifecycle.get(
        "DeleteAfterDays"
    )

    return (
        move_to_cold is not None
        or delete_after is not None
    )


# ============================================================
# GET LIFECYCLE DETAILS
# ============================================================

def get_lifecycle_details(
    recovery_point: Dict[str, Any],
) -> Dict[str, Any]:

    lifecycle = (
        recovery_point.get(
            "Lifecycle"
        )
        or {}
    )

    return {

        "moveToColdStorageAfterDays":
            lifecycle.get(
                "MoveToColdStorageAfterDays"
            ),

        "deleteAfterDays":
            lifecycle.get(
                "DeleteAfterDays"
            ),
    }


# ============================================================
# GET RESOURCE INFORMATION
# ============================================================

def get_resource_information(
    recovery_point: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Extract the resource protected by the recovery point.
    """

    resource_arn = (
        recovery_point.get(
            "ResourceArn"
        )
    )

    resource_type = (
        recovery_point.get(
            "ResourceType"
        )
    )

    return {

        "resourceArn": resource_arn,

        "resourceType": resource_type,
    }


# ============================================================
# GET BACKUP SIZE
# ============================================================

def get_backup_size(
    recovery_point: Dict[str, Any],
) -> Dict[str, Any]:

    size_bytes = (
        recovery_point.get(
            "BackupSizeInBytes"
        )
    )

    size_gb = None

    if size_bytes is not None:

        size_gb = round(
            size_bytes / (1024 ** 3),
            4,
        )

    return {

        "backupSizeBytes": size_bytes,

        "backupSizeGB": size_gb,
    }


# ============================================================
# BUILD RESOURCE ID
# ============================================================

def get_resource_id(
    recovery_point: Dict[str, Any],
) -> str | None:
    """
    Extract a useful resource ID from ResourceArn.

    Examples:

        arn:aws:ec2:region:account:volume/vol-xxx

        arn:aws:ec2:region:account:image/ami-xxx

    """

    resource_arn = (
        recovery_point.get(
            "ResourceArn"
        )
    )

    if not resource_arn:
        return None

    # Handle common ARN resource formats.

    if "/" in resource_arn:

        return resource_arn.rsplit(
            "/",
            1
        )[-1]

    if ":" in resource_arn:

        return resource_arn.rsplit(
            ":",
            1
        )[-1]

    return resource_arn


# ============================================================
# BUILD RESOURCE NAME
# ============================================================

def get_resource_name_or_id(
    recovery_point: Dict[str, Any],
) -> str | None:

    resource_id = get_resource_id(
        recovery_point
    )

    if resource_id:
        return resource_id

    return (
        recovery_point.get(
            "RecoveryPointArn"
        )
    )


# ============================================================
# COST LOOKUP
# ============================================================

def get_resource_cost(
    account_id: str,
    region_name: str,
    resource_arn: str | None,
) -> Dict[str, Any]:
    """
    Cost values are intentionally not calculated here.

    Your architecture should have a separate CUR + Athena
    cost engine.

    This function is the integration point.

    CUR/Athena should eventually return:

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
    recovery_point: Dict[str, Any],
    backup_vault_name: str,
    age_days: float,
) -> str:

    recovery_point_arn = (
        recovery_point.get(
            "RecoveryPointArn"
        )
    )

    resource_type = (
        recovery_point.get(
            "ResourceType"
        )
        or "unknown"
    )

    resource_id = (
        get_resource_id(
            recovery_point
        )
        or "unknown"
    )

    return (

        f"Recovery point "
        f"{recovery_point_arn} "

        f"for {resource_type} "
        f"{resource_id} "

        f"in vault {backup_vault_name} "
        f"is {int(age_days)} days old "
        f"and has no lifecycle policy. "

        f"Review the retention requirement. "

        f"Consider configuring a lifecycle policy "
        f"to transition eligible recovery points "
        f"to cold storage and/or delete them after "
        f"the required retention period."
    )


# ============================================================
# BUILD FINOPS FINDING
# ============================================================

def build_recovery_point_finding(
    recovery_point: Dict[str, Any],
    backup_vault: Dict[str, Any],
    account_id: str,
    region_name: str,
) -> Dict[str, Any]:

    # --------------------------------------------------------
    # Backup Vault
    # --------------------------------------------------------

    backup_vault_name = (
        backup_vault.get(
            "BackupVaultName"
        )
    )

    backup_vault_arn = (
        backup_vault.get(
            "BackupVaultArn"
        )
    )

    # --------------------------------------------------------
    # Recovery Point
    # --------------------------------------------------------

    recovery_point_arn = (
        recovery_point.get(
            "RecoveryPointArn"
        )
    )

    recovery_point_type = (
        recovery_point.get(
            "RecoveryPointType"
        )
    )

    status = (
        recovery_point.get(
            "Status"
        )
    )

    # --------------------------------------------------------
    # Resource
    # --------------------------------------------------------

    resource_info = (
        get_resource_information(
            recovery_point
        )
    )

    resource_arn = (
        resource_info[
            "resourceArn"
        ]
    )

    resource_type = (
        resource_info[
            "resourceType"
        ]
    )

    resource_id = (
        get_resource_id(
            recovery_point
        )
    )

    # --------------------------------------------------------
    # Dates
    # --------------------------------------------------------

    creation_date = (
        recovery_point.get(
            "CreationDate"
        )
    )

    completion_date = (
        recovery_point.get(
            "CompletionDate"
        )
    )

    age_days = calculate_age_days(
        creation_date
    )

    # --------------------------------------------------------
    # Lifecycle
    # --------------------------------------------------------

    lifecycle = (
        get_lifecycle_details(
            recovery_point
        )
    )

    move_to_cold_storage_after_days = (
        lifecycle[
            "moveToColdStorageAfterDays"
        ]
    )

    delete_after_days = (
        lifecycle[
            "deleteAfterDays"
        ]
    )

    # --------------------------------------------------------
    # Backup Size
    # --------------------------------------------------------

    backup_size = (
        get_backup_size(
            recovery_point
        )
    )

    backup_size_bytes = (
        backup_size[
            "backupSizeBytes"
        ]
    )

    backup_size_gb = (
        backup_size[
            "backupSizeGB"
        ]
    )

    # --------------------------------------------------------
    # Cost
    # --------------------------------------------------------

    cost = get_resource_cost(

        account_id=account_id,

        region_name=region_name,

        resource_arn=(
            recovery_point_arn
        ),
    )

    # --------------------------------------------------------
    # Recommendation
    # --------------------------------------------------------

    recommendation = (
        build_recommendation(

            recovery_point=(
                recovery_point
            ),

            backup_vault_name=(
                backup_vault_name
            ),

            age_days=(
                age_days
            ),
        )
    )

    # --------------------------------------------------------
    # Message
    # --------------------------------------------------------

    message = (

        f"Recovery point "

        f"{recovery_point_arn} "

        f"in vault {backup_vault_name} "

        f"is {int(age_days)} days old "

        f"and has no lifecycle policy. "

        f"Review retention requirements and "

        f"consider adding a lifecycle policy "
        f"to transition eligible recovery points "
        f"to cold storage or delete them after "
        f"the required retention period."
    )

    # --------------------------------------------------------
    # ARN
    # --------------------------------------------------------

    arn = recovery_point_arn

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    description = (

        f"accountId: {account_id} | "

        f"region: {region_name} | "

        f"resourceId: "
        f"{resource_id} | "

        f"arn: {arn} | "

        f"Type: Recovery Point Without Lifecycle | "

        f"policy: {POLICY_NAME} | "

        f"message: {message} | "

        f"effortLevel: {EFFORT_LEVEL} | "

        f"backupVault: "
        f"{backup_vault_name} | "

        f"resourceType: "
        f"{resource_type} | "

        f"ageDays: "
        f"{age_days} | "

        f"backupSizeGB: "
        f"{backup_size_gb}"
    )

    # --------------------------------------------------------
    # Return Finding
    # --------------------------------------------------------

    return {

        # ====================================================
        # WORKFLOW
        # ====================================================

        "workItemType": "Task",

        "state": "To Do",

        "title": (
            "Backup Recovery Point with Lifecycle"
        ),

        "category": CATEGORY,

        "owner": "",

        "assignedTo": "",

        "status": "Pending for Review",

        "areaPath": (
            "AWS Cost Optimization"
        ),

        "tags": "",

        "commentCount": 0,

        # ====================================================
        # AWS IDENTITY
        # ====================================================

        "accountId": account_id,

        "region": region_name,

        "resourceNameOrId": (
            resource_id
            or recovery_point_arn
        ),

        "resourceId": (
            resource_id
        ),

        "resourceArn": (
            recovery_point_arn
        ),

        "service": SERVICE_NAME,

        # ====================================================
        # BACKUP VAULT
        # ====================================================

        "backupVaultName": (
            backup_vault_name
        ),

        "backupVaultArn": (
            backup_vault_arn
        ),

        # ====================================================
        # RECOVERY POINT
        # ====================================================

        "recoveryPointArn": (
            recovery_point_arn
        ),

        "recoveryPointType": (
            recovery_point_type
        ),

        "resourceType": (
            resource_type
        ),

        "sourceResourceArn": (
            resource_arn
        ),

        "status": status,

        # ====================================================
        # DATES
        # ====================================================

        "creationDate": (

            creation_date.isoformat()

            if creation_date

            else None
        ),

        "completionDate": (

            completion_date.isoformat()

            if completion_date

            else None
        ),

        "ageDays": age_days,

        # ====================================================
        # SIZE
        # ====================================================

        "backupSizeBytes": (
            backup_size_bytes
        ),

        "backupSizeGB": (
            backup_size_gb
        ),

        # ====================================================
        # LIFECYCLE
        # ====================================================

        "hasLifecyclePolicy": False,

        "moveToColdStorageAfterDays": (
            move_to_cold_storage_after_days
        ),

        "deleteAfterDays": (
            delete_after_days
        ),

        # ====================================================
        # FINOPS
        # ====================================================

        "type": (
            "Recovery Point Without Lifecycle"
        ),

        "policy": POLICY_NAME,

        "effortLevel": EFFORT_LEVEL,

        "recommendation": (
            recommendation
        ),

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
# SCAN BACKUP VAULT
# ============================================================

def scan_backup_vault(
    backup,
    backup_vault: Dict[str, Any],
    account_id: str,
    region_name: str,
) -> Dict[str, Any]:
    """
    Scan all recovery points in one Backup Vault.
    """

    backup_vault_name = (
        backup_vault.get(
            "BackupVaultName"
        )
    )

    print(
        f"\nScanning Backup Vault: "
        f"{backup_vault_name}"
    )

    # --------------------------------------------------------
    # Fetch recovery points
    # --------------------------------------------------------

    recovery_points = (
        fetch_all_recovery_points(

            backup=backup,

            backup_vault_name=(
                backup_vault_name
            ),
        )
    )

    findings = []

    # --------------------------------------------------------
    # Process each recovery point
    # --------------------------------------------------------

    for recovery_point in recovery_points:

        creation_date = (
            recovery_point.get(
                "CreationDate"
            )
        )

        age_days = calculate_age_days(
            creation_date
        )

        # ----------------------------------------------------
        # Check age
        # ----------------------------------------------------

        if not is_old_recovery_point(
            age_days
        ):

            continue

        # ----------------------------------------------------
        # Check lifecycle
        # ----------------------------------------------------

        if has_lifecycle_policy(
            recovery_point
        ):

            continue

        # ----------------------------------------------------
        # Build finding
        # ----------------------------------------------------

        finding = (
            build_recovery_point_finding(

                recovery_point=(
                    recovery_point
                ),

                backup_vault=(
                    backup_vault
                ),

                account_id=(
                    account_id
                ),

                region_name=(
                    region_name
                ),
            )
        )

        findings.append(
            finding
        )

    # --------------------------------------------------------
    # Return vault result
    # --------------------------------------------------------

    return {

        "backupVaultName": (
            backup_vault_name
        ),

        "totalRecoveryPointsScanned": (
            len(recovery_points)
        ),

        "totalFindings": (
            len(findings)
        ),

        "findings": findings,
    }


# ============================================================
# SCAN ALL BACKUP VAULTS
# ============================================================

def scan_backup_recovery_points(
    region_name: str,
) -> Dict[str, Any]:
    """
    Automatically discover and scan every Backup Vault
    and every Recovery Point in the supplied region.
    """

    backup, sts = create_clients(
        region_name
    )

    account_id = get_account_id(
        sts
    )

    # --------------------------------------------------------
    # Fetch all Backup Vaults
    # --------------------------------------------------------

    backup_vaults = (
        fetch_all_backup_vaults(
            backup
        )
    )

    all_findings = []

    vault_inventory = []

    total_recovery_points = 0

    # --------------------------------------------------------
    # Process every Backup Vault
    # --------------------------------------------------------

    for backup_vault in backup_vaults:

        result = (
            scan_backup_vault(

                backup=backup,

                backup_vault=(
                    backup_vault
                ),

                account_id=(
                    account_id
                ),

                region_name=(
                    region_name
                ),
            )
        )

        # ----------------------------------------------------
        # Findings
        # ----------------------------------------------------

        all_findings.extend(
            result[
                "findings"
            ]
        )

        # ----------------------------------------------------
        # Count
        # ----------------------------------------------------

        total_recovery_points += (
            result[
                "totalRecoveryPointsScanned"
            ]
        )

        # ----------------------------------------------------
        # Inventory
        # ----------------------------------------------------

        vault_inventory.append({

            "accountId": account_id,

            "region": region_name,

            "backupVaultName": (
                result[
                    "backupVaultName"
                ]
            ),

            "totalRecoveryPoints": (
                result[
                    "totalRecoveryPointsScanned"
                ]
            ),

            "findings": (
                result[
                    "totalFindings"
                ]
            ),
        })

    # --------------------------------------------------------
    # Final Result
    # --------------------------------------------------------

    return {

        "accountId": account_id,

        "region": region_name,

        "totalBackupVaultsScanned": (
            len(backup_vaults)
        ),

        "totalRecoveryPointsScanned": (
            total_recovery_points
        ),

        "totalRecoveryPointsWithoutLifecycle": (
            len(all_findings)
        ),

        "findings": all_findings,

        "backupVaultInventory": (
            vault_inventory
        ),
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
    # ONLY REGION IS PROVIDED.
    #
    # Backup Vaults and Recovery Points are discovered
    # automatically.
    # --------------------------------------------------------

    region = "eu-west-1"

    print(
        "\n=========================================="
    )

    print(
        "AWS BACKUP RECOVERY POINT SCANNER"
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
        "Age threshold:",
        RECOVERY_POINT_AGE_THRESHOLD_DAYS,
        "days"
    )

    print(
        "=========================================="
    )

    # --------------------------------------------------------
    # Scan
    # --------------------------------------------------------

    result = (
        scan_backup_recovery_points(
            region
        )
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
        "Backup Vaults:",
        result[
            "totalBackupVaultsScanned"
        ]
    )

    print(
        "Recovery Points:",
        result[
            "totalRecoveryPointsScanned"
        ]
    )

    print(
        "Findings:",
        result[
            "totalRecoveryPointsWithoutLifecycle"
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
            "\nNo old Backup Recovery Points "
            "without lifecycle policy found."
        )

    # --------------------------------------------------------
    # Export Excel
    # --------------------------------------------------------

    excel_file = (
        "backup_recovery_point_lifecycle_report.xlsx"
    )

    export_to_excel(
        findings=findings,

        filename=excel_file,
    )

    print(
        "\nCompleted."
    )

