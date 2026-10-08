# ============================================================
# AWS FinOps Policy
# Policy: Delete or Move to Archive Tier
# Service: RDS Snapshot
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

OUTPUT_FILE = "rds_snapshot_delete_or_archive.xlsx"

AWS_CONFIG = Config(
    retries={
        "max_attempts": 10,
        "mode": "adaptive"
    }
)


# ============================================================
# 3. FinOps Policy Configuration
# ============================================================

POLICY_TITLE = "Delete or Move to Archive Tier"

CATEGORY = "RDS Snapshot Optimization"

SERVICE = "RDS Snapshot"

# Snapshot age threshold.
# Snapshots older than this are considered candidates
# for review.
SNAPSHOT_AGE_THRESHOLD_DAYS = 7

# Only snapshots in these states are considered.
VALID_SNAPSHOT_STATES = {
    "available"
}


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


# ============================================================
# 7. Fetch Additional AWS Data / Metrics
# ============================================================

def build_db_instance_map(db_instances):

    instance_map = {}

    for instance in db_instances:

        identifier = instance.get(
            "DBInstanceIdentifier"
        )

        if not identifier:
            continue

        instance_map[identifier] = {
            "DBInstanceIdentifier": identifier,
            "DBInstanceArn": instance.get(
                "DBInstanceArn"
            ),
            "DBInstanceStatus": instance.get(
                "DBInstanceStatus"
            ),
            "Engine": instance.get(
                "Engine"
            ),
            "EngineVersion": instance.get(
                "EngineVersion"
            ),
            "AllocatedStorage": instance.get(
                "AllocatedStorage"
            ),
            "BackupRetentionPeriod": instance.get(
                "BackupRetentionPeriod"
            ),
            "StorageEncrypted": instance.get(
                "StorageEncrypted"
            ),
            "DeletionProtection": instance.get(
                "DeletionProtection"
            ),
            "TagList": instance.get(
                "TagList",
                []
            )
        }

    return instance_map


def convert_tags_to_dict(tag_list):

    tags = {}

    for tag in tag_list or []:

        key = tag.get("Key")
        value = tag.get("Value")

        if key:
            tags[key] = value

    return tags


def calculate_age_days(snapshot_time):

    if not snapshot_time:
        return None

    now = datetime.now(timezone.utc)

    if snapshot_time.tzinfo is None:

        snapshot_time = snapshot_time.replace(
            tzinfo=timezone.utc
        )

    age = now - snapshot_time

    return age.days


def get_snapshot_source_status(
    snapshot,
    db_instance_map
):

    source_identifier = snapshot.get(
        "DBInstanceIdentifier"
    )

    if not source_identifier:

        return (
            None,
            False,
            None
        )

    source_instance = db_instance_map.get(
        source_identifier
    )

    if not source_instance:

        return (
            source_identifier,
            False,
            None
        )

    return (
        source_identifier,
        True,
        source_instance
    )


# ============================================================
# 8. Evaluate FinOps Policy
# ============================================================

def evaluate_snapshot(
    snapshot,
    db_instance_map,
    account_id,
    region
):

    snapshot_type = snapshot.get(
        "SnapshotType"
    )

    snapshot_status = snapshot.get(
        "Status"
    )

    snapshot_identifier = snapshot.get(
        "DBSnapshotIdentifier"
    )

    snapshot_arn = snapshot.get(
        "DBSnapshotArn"
    )

    source_identifier = snapshot.get(
        "DBInstanceIdentifier"
    )

    created_time = snapshot.get(
        "SnapshotCreateTime"
    )

    allocated_storage = snapshot.get(
        "AllocatedStorage"
    )

    encrypted = snapshot.get(
        "Encrypted"
    )

    engine = snapshot.get(
        "Engine"
    )

    engine_version = snapshot.get(
        "EngineVersion"
    )

    tags = convert_tags_to_dict(
        snapshot.get(
            "TagList",
            []
        )
    )

    age_days = calculate_age_days(
        created_time
    )

    # --------------------------------------------------------
    # Source DB instance
    # --------------------------------------------------------

    (
        source_identifier,
        source_available,
        source_instance
    ) = get_snapshot_source_status(
        snapshot,
        db_instance_map
    )

    # --------------------------------------------------------
    # Backup retention
    # --------------------------------------------------------

    retention_days = None

    if source_instance:

        retention_days = source_instance.get(
            "BackupRetentionPeriod"
        )

    # --------------------------------------------------------
    # Orphan detection
    # --------------------------------------------------------

    is_orphaned = not source_available

    # --------------------------------------------------------
    # Policy evaluation
    # --------------------------------------------------------

    if snapshot_type != "automated":
        return None

    if snapshot_status not in VALID_SNAPSHOT_STATES:
        return None

    if age_days is None:
        return None

    if age_days < SNAPSHOT_AGE_THRESHOLD_DAYS:
        return None

    return {
        "account_id": account_id,
        "region": region,
        "snapshot_id": snapshot_identifier,
        "snapshot_arn": snapshot_arn,
        "snapshot_type": snapshot_type,
        "snapshot_status": snapshot_status,
        "created_date": created_time,
        "age_days": age_days,
        "size_gb": allocated_storage,
        "encrypted": encrypted,
        "engine": engine,
        "engine_version": engine_version,
        "source_resource": source_identifier,
        "source_available": source_available,
        "retention_days": retention_days,
        "is_orphaned": is_orphaned,
        "tags": tags
    }


# ============================================================
# 9. Build FinOps Finding
# ============================================================

def build_finding(evaluation):

    account_id = evaluation[
        "account_id"
    ]

    region = evaluation[
        "region"
    ]

    snapshot_id = evaluation[
        "snapshot_id"
    ]

    snapshot_type = evaluation[
        "snapshot_type"
    ]

    snapshot_status = evaluation[
        "snapshot_status"
    ]

    created_date = evaluation[
        "created_date"
    ]

    age_days = evaluation[
        "age_days"
    ]

    size_gb = evaluation[
        "size_gb"
    ]

    encrypted = evaluation[
        "encrypted"
    ]

    engine = evaluation[
        "engine"
    ]

    source_resource = evaluation[
        "source_resource"
    ]

    source_available = evaluation[
        "source_available"
    ]

    retention_days = evaluation[
        "retention_days"
    ]

    is_orphaned = evaluation[
        "is_orphaned"
    ]

    tags = evaluation[
        "tags"
    ]

    # --------------------------------------------------------
    # Determine recommendation
    # --------------------------------------------------------

    if is_orphaned:

        recommendation = (
            "Review retained automated backup. "
            "Source DB instance is no longer available."
        )

    else:

        recommendation = (
            "Review RDS backup retention policy. "
            "For automated snapshots, optimize the source "
            "DB instance backup retention period rather than "
            "deleting the individual automated snapshot."
        )

    # --------------------------------------------------------
    # Tags
    # --------------------------------------------------------

    tags_text = str(tags)

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    description = (
        f"BackupType: RDS_automated_snapshot | "
        f"State: {snapshot_status} | "
        f"CreatedDate: "
        f"{created_date.strftime('%d-%m-%Y') if created_date else ''} | "
        f"AgeDays: {age_days} | "
        f"SizeGB: {size_gb} | "
        f"Encrypted: "
        f"{'Yes' if encrypted else 'No'} | "
        f"SourceResource: {source_resource or ''} | "
        f"SourceAvailable: "
        f"{'Yes' if source_available else 'No'} | "
        f"RetentionDays: "
        f"{retention_days if retention_days is not None else ''} | "
        f"Engine: {engine or ''} | "
        f"Tags: {tags_text} | "
        f"IsOrphaned: "
        f"{'Yes' if is_orphaned else 'No'} | "
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
        "tags": "CLX",
        "commentCount": 0,
        "accountId": account_id,
        "region": region,
        "resourceNameOrId": f"rds:{snapshot_id}",
        "resourceId": snapshot_id,
        "resourceArn": "",
        "service": SERVICE,
        "type": "RDS Snapshot",
        "policy": POLICY_TITLE,
        "effortLevel": "Medium",
        "message": "Review RDS backup retention policy.",
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
    # Fetch RDS instances
    # --------------------------------------------------------

    print(
        "Fetching RDS instances..."
    )

    db_instances = fetch_all_rds_instances(
        rds
    )

    print(
        f"RDS instances scanned: "
        f"{len(db_instances)}"
    )

    # --------------------------------------------------------
    # Build instance lookup
    # --------------------------------------------------------

    db_instance_map = build_db_instance_map(
        db_instances
    )

    # --------------------------------------------------------
    # Evaluate snapshots
    # --------------------------------------------------------

    findings = []

    for snapshot in snapshots:

        evaluation = evaluate_snapshot(
            snapshot,
            db_instance_map,
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
    # Excel columns
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
        f"RDS Snapshots Scanned  : "
        f"{len(snapshots)}"
    )

    print(
        f"RDS Instances Scanned  : "
        f"{len(db_instances)}"
    )

    print(
        f"FinOps Candidates      : "
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