# ============================================================
# AWS FinOps Policy
# Policy: Delete Stopped RDS instances
# Service: RDS
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

OUTPUT_FILE = "delete_stopped_rds_instances.xlsx"

AWS_CONFIG = Config(
    retries={
        "max_attempts": 10,
        "mode": "adaptive"
    }
)


# ============================================================
# 3. FinOps Policy Configuration
# ============================================================

POLICY_TITLE = "Delete Stopped RDS instances"

CATEGORY = "Delete Stopped RDS instances"

SERVICE = "RDS"

TARGET_STATE = "stopped"


# ============================================================
# 4. Create AWS Clients
# ============================================================

def create_clients(region_name):

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

    return rds, sts


# ============================================================
# 5. Get Account ID
# ============================================================

def get_account_id(sts):

    return sts.get_caller_identity()["Account"]


# ============================================================
# 6. Fetch All Resources with Pagination
# ============================================================

def fetch_all_rds_instances(rds):

    instances = []

    marker = None

    while True:

        params = {}

        if marker:
            params["Marker"] = marker

        response = rds.describe_db_instances(
            **params
        )

        instances.extend(
            response.get(
                "DBInstances",
                []
            )
        )

        marker = response.get(
            "Marker"
        )

        if not marker:
            break

    return instances


def fetch_all_rds_snapshots(rds):

    snapshots = []

    marker = None

    while True:

        params = {}

        if marker:
            params["Marker"] = marker

        response = rds.describe_db_snapshots(
            **params
        )

        snapshots.extend(
            response.get(
                "DBSnapshots",
                []
            )
        )

        marker = response.get(
            "Marker"
        )

        if not marker:
            break

    return snapshots


# ============================================================
# 7. Fetch Additional AWS Data / Metrics
# ============================================================

def build_snapshot_map(snapshots):

    snapshot_map = {}

    for snapshot in snapshots:

        db_identifier = snapshot.get(
            "DBInstanceIdentifier"
        )

        if not db_identifier:
            continue

        status = snapshot.get(
            "Status"
        )

        if status != "available":
            continue

        snapshot_details = {
            "snapshot_id": snapshot.get(
                "DBSnapshotIdentifier"
            ),
            "snapshot_type": snapshot.get(
                "SnapshotType"
            ),
            "snapshot_create_time": snapshot.get(
                "SnapshotCreateTime"
            ),
            "allocated_storage": snapshot.get(
                "AllocatedStorage"
            ),
            "encrypted": snapshot.get(
                "Encrypted"
            ),
            "engine": snapshot.get(
                "Engine"
            )
        }

        snapshot_map.setdefault(
            db_identifier,
            []
        ).append(
            snapshot_details
        )

    return snapshot_map


def get_instance_tags(instance):

    tags = {}

    for tag in instance.get(
        "TagList",
        []
    ):

        key = tag.get("Key")
        value = tag.get("Value")

        if key:
            tags[key] = value

    return tags


def calculate_instance_age_days(
    creation_time
):

    if not creation_time:
        return None

    if creation_time.tzinfo is None:

        creation_time = creation_time.replace(
            tzinfo=timezone.utc
        )

    now = datetime.now(
        timezone.utc
    )

    return (
        now - creation_time
    ).days


def get_latest_snapshot(
    snapshots
):

    if not snapshots:
        return None

    valid_snapshots = [
        snapshot
        for snapshot in snapshots
        if snapshot.get(
            "snapshot_create_time"
        )
    ]

    if not valid_snapshots:
        return None

    return max(
        valid_snapshots,
        key=lambda x: x[
            "snapshot_create_time"
        ]
    )


# ============================================================
# 8. Evaluate FinOps Policy
# ============================================================

def evaluate_rds_instance(
    instance,
    snapshot_map,
    account_id,
    region
):

    instance_id = instance.get(
        "DBInstanceIdentifier"
    )

    state = instance.get(
        "DBInstanceStatus"
    )

    # --------------------------------------------------------
    # Policy condition
    # --------------------------------------------------------

    if state != TARGET_STATE:
        return None

    instance_arn = instance.get(
        "DBInstanceArn"
    )

    engine = instance.get(
        "Engine"
    )

    engine_version = instance.get(
        "EngineVersion"
    )

    instance_class = instance.get(
        "DBInstanceClass"
    )

    allocated_storage = instance.get(
        "AllocatedStorage"
    )

    storage_type = instance.get(
        "StorageType"
    )

    encrypted = instance.get(
        "StorageEncrypted"
    )

    multi_az = instance.get(
        "MultiAZ"
    )

    availability_zone = instance.get(
        "AvailabilityZone"
    )

    creation_time = instance.get(
        "InstanceCreateTime"
    )

    backup_retention_days = instance.get(
        "BackupRetentionPeriod"
    )

    deletion_protection = instance.get(
        "DeletionProtection"
    )

    publicly_accessible = instance.get(
        "PubliclyAccessible"
    )

    auto_minor_version_upgrade = instance.get(
        "AutoMinorVersionUpgrade"
    )

    tags = get_instance_tags(
        instance
    )

    # --------------------------------------------------------
    # Instance age
    # --------------------------------------------------------

    age_days = calculate_instance_age_days(
        creation_time
    )

    # --------------------------------------------------------
    # Snapshot information
    # --------------------------------------------------------

    snapshots = snapshot_map.get(
        instance_id,
        []
    )

    latest_snapshot = get_latest_snapshot(
        snapshots
    )

    snapshot_count = len(
        snapshots
    )

    automated_snapshot_count = len(
        [
            snapshot
            for snapshot in snapshots
            if snapshot.get(
                "snapshot_type"
            ) == "automated"
        ]
    )

    manual_snapshot_count = len(
        [
            snapshot
            for snapshot in snapshots
            if snapshot.get(
                "snapshot_type"
            ) == "manual"
        ]
    )

    # --------------------------------------------------------
    # Return evaluation
    # --------------------------------------------------------

    return {
        "account_id": account_id,
        "region": region,
        "instance_id": instance_id,
        "instance_arn": instance_arn,
        "state": state,
        "engine": engine,
        "engine_version": engine_version,
        "instance_class": instance_class,
        "allocated_storage": allocated_storage,
        "storage_type": storage_type,
        "encrypted": encrypted,
        "multi_az": multi_az,
        "availability_zone": availability_zone,
        "creation_time": creation_time,
        "age_days": age_days,
        "backup_retention_days": backup_retention_days,
        "deletion_protection": deletion_protection,
        "publicly_accessible": publicly_accessible,
        "auto_minor_version_upgrade": (
            auto_minor_version_upgrade
        ),
        "tags": tags,
        "snapshot_count": snapshot_count,
        "automated_snapshot_count": (
            automated_snapshot_count
        ),
        "manual_snapshot_count": (
            manual_snapshot_count
        ),
        "latest_snapshot": latest_snapshot
    }


# ============================================================
# 9. Build FinOps Finding
# ============================================================

def build_finding(
    evaluation
):

    account_id = evaluation[
        "account_id"
    ]

    region = evaluation[
        "region"
    ]

    instance_id = evaluation[
        "instance_id"
    ]

    state = evaluation[
        "state"
    ]

    engine = evaluation[
        "engine"
    ]

    engine_version = evaluation[
        "engine_version"
    ]

    instance_class = evaluation[
        "instance_class"
    ]

    allocated_storage = evaluation[
        "allocated_storage"
    ]

    storage_type = evaluation[
        "storage_type"
    ]

    encrypted = evaluation[
        "encrypted"
    ]

    multi_az = evaluation[
        "multi_az"
    ]

    availability_zone = evaluation[
        "availability_zone"
    ]

    creation_time = evaluation[
        "creation_time"
    ]

    age_days = evaluation[
        "age_days"
    ]

    backup_retention_days = evaluation[
        "backup_retention_days"
    ]

    deletion_protection = evaluation[
        "deletion_protection"
    ]

    publicly_accessible = evaluation[
        "publicly_accessible"
    ]

    auto_minor_version_upgrade = evaluation[
        "auto_minor_version_upgrade"
    ]

    tags = evaluation[
        "tags"
    ]

    snapshot_count = evaluation[
        "snapshot_count"
    ]

    automated_snapshot_count = evaluation[
        "automated_snapshot_count"
    ]

    manual_snapshot_count = evaluation[
        "manual_snapshot_count"
    ]

    latest_snapshot = evaluation[
        "latest_snapshot"
    ]

    # --------------------------------------------------------
    # Latest snapshot details
    # --------------------------------------------------------

    latest_snapshot_id = ""

    latest_snapshot_date = ""

    latest_snapshot_type = ""

    if latest_snapshot:

        latest_snapshot_id = (
            latest_snapshot.get(
                "snapshot_id"
            )
            or ""
        )

        latest_snapshot_type = (
            latest_snapshot.get(
                "snapshot_type"
            )
            or ""
        )

        snapshot_time = (
            latest_snapshot.get(
                "snapshot_create_time"
            )
        )

        if snapshot_time:

            latest_snapshot_date = (
                snapshot_time.strftime(
                    "%d-%m-%Y %H:%M:%S"
                )
            )

    # --------------------------------------------------------
    # Backup status
    # --------------------------------------------------------

    if snapshot_count > 0:

        backup_status = (
            f"AvailableSnapshots: "
            f"{snapshot_count} | "
            f"AutomatedSnapshots: "
            f"{automated_snapshot_count} | "
            f"ManualSnapshots: "
            f"{manual_snapshot_count}"
        )

    else:

        backup_status = (
            "AvailableSnapshots: 0 | "
            "BackupRequiredBeforeDeletion: Yes"
        )

    # --------------------------------------------------------
    # Recommendation
    # --------------------------------------------------------

    recommendation = (
        "RDS instance is in stopped state. "
        "Validate ownership and business requirement. "
        "Ensure a required backup/snapshot is available "
        "before deletion. If the instance is no longer "
        "required, delete the RDS instance after approval."
    )

    # --------------------------------------------------------
    # Tags
    # --------------------------------------------------------

    tags_text = str(tags)

    # --------------------------------------------------------
    # Created date
    # --------------------------------------------------------

    created_date_text = ""

    if creation_time:

        created_date_text = (
            creation_time.strftime(
                "%d-%m-%Y"
            )
        )

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    description = (
        f"State: {state} | "
        f"CreatedDate: {created_date_text} | "
        f"AgeDays: {age_days} | "
        f"Engine: {engine} | "
        f"EngineVersion: {engine_version} | "
        f"InstanceClass: {instance_class} | "
        f"StorageGB: {allocated_storage} | "
        f"StorageType: {storage_type} | "
        f"Encrypted: "
        f"{'Yes' if encrypted else 'No'} | "
        f"MultiAZ: "
        f"{'Yes' if multi_az else 'No'} | "
        f"AvailabilityZone: {availability_zone} | "
        f"BackupRetentionDays: "
        f"{backup_retention_days} | "
        f"DeletionProtection: "
        f"{'Enabled' if deletion_protection else 'Disabled'} | "
        f"PubliclyAccessible: "
        f"{'Yes' if publicly_accessible else 'No'} | "
        f"AutoMinorVersionUpgrade: "
        f"{'Enabled' if auto_minor_version_upgrade else 'Disabled'} | "
        f"SnapshotCount: {snapshot_count} | "
        f"AutomatedSnapshotCount: "
        f"{automated_snapshot_count} | "
        f"ManualSnapshotCount: "
        f"{manual_snapshot_count} | "
        f"LatestSnapshot: "
        f"{latest_snapshot_id} | "
        f"LatestSnapshotType: "
        f"{latest_snapshot_type} | "
        f"LatestSnapshotDate: "
        f"{latest_snapshot_date} | "
        f"Tags: {tags_text} | "
        f"{backup_status} | "
        f"Recommendation: {recommendation}"
    )

    # --------------------------------------------------------
    # Finding
    # --------------------------------------------------------

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
        "resourceNameOrId": instance_id,
        "resourceId": instance_id,
        "resourceArn": "",
        "service": SERVICE,
        "type": "RDS Instance",
        "policy": POLICY_TITLE,
        "effortLevel": "Medium",
        "message": "RDS instance is in stopped state.",
        "recommendation": recommendation,
        "description": description,
        "currentDailyCost": "To be updated",
        "currentMonthlyCost": "To be updated",
        "estimatedMonthlySavings": "To be updated",
        "approvalComments": "",
        "reasonForRejection": "",
        "achievedSavingsMonthly": "",
        "month": ""
    }


# ============================================================
# 10. Main Execution
# ============================================================

def main():

    scan_start_time = datetime.now(
        timezone.utc
    )

    print("=" * 75)
    print("AWS FinOps Policy Scan")
    print("=" * 75)

    print(
        f"Policy : {POLICY_TITLE}"
    )

    print(
        f"Service: {SERVICE}"
    )

    print(
        f"Region : {REGION}"
    )

    print("=" * 75)

    # --------------------------------------------------------
    # Create clients
    # --------------------------------------------------------

    rds, sts = create_clients(
        REGION
    )

    # --------------------------------------------------------
    # Account ID
    # --------------------------------------------------------

    account_id = get_account_id(
        sts
    )

    print(
        f"Account ID: {account_id}"
    )

    # --------------------------------------------------------
    # Fetch RDS instances
    # --------------------------------------------------------

    print(
        "Fetching RDS instances..."
    )

    instances = fetch_all_rds_instances(
        rds
    )

    print(
        f"RDS instances scanned: "
        f"{len(instances)}"
    )

    # --------------------------------------------------------
    # Fetch RDS snapshots
    # --------------------------------------------------------

    print(
        "Fetching RDS snapshots..."
    )

    snapshots = fetch_all_rds_snapshots(
        rds
    )

    print(
        f"RDS snapshots scanned: "
        f"{len(snapshots)}"
    )

    # --------------------------------------------------------
    # Build snapshot lookup
    # --------------------------------------------------------

    snapshot_map = build_snapshot_map(
        snapshots
    )

    # --------------------------------------------------------
    # Evaluate RDS instances
    # --------------------------------------------------------

    findings = []

    for instance in instances:

        evaluation = evaluate_rds_instance(
            instance,
            snapshot_map,
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
    # Calculate Pricing Savings
    # --------------------------------------------------------
    
    try:
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        import delete_stopped_rds_pricing
        
        if findings:
            findings = delete_stopped_rds_pricing.calculate_savings(findings, account_id=account_id)
            print(f"Successfully enriched {len(findings)} findings with pricing data.")
    except Exception as e:
        print(f"Warning: Failed to execute pricing calculation. {e}")

    # --------------------------------------------------------
    # Fixed Excel Schema
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

    # --------------------------------------------------------
    # Scan duration
    # --------------------------------------------------------

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
    print("=" * 75)
    print("SCAN SUMMARY")
    print("=" * 75)

    print(
        f"Account ID             : "
        f"{account_id}"
    )

    print(
        f"Region                 : "
        f"{REGION}"
    )

    print(
        f"RDS Instances Scanned  : "
        f"{len(instances)}"
    )

    print(
        f"RDS Snapshots Scanned  : "
        f"{len(snapshots)}"
    )

    print(
        f"Stopped RDS Candidates : "
        f"{len(findings)}"
    )

    print(
        f"Scan Duration          : "
        f"{scan_duration:.2f} seconds"
    )

    print(
        f"Excel Output           : "
        f"{OUTPUT_FILE}"
    )

    print("=" * 75)


if __name__ == "__main__":
    main()