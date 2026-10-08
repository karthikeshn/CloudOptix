# ============================================================
# AWS FinOps Policy
# Policy: EBS Volume Stopped
# Service: EBS
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

OUTPUT_FILE = (
    "ebs_volume_stopped.xlsx"
)

AWS_CONFIG = Config(
    retries={
        "max_attempts": 10,
        "mode": "adaptive"
    }
)


# ============================================================
# 3. FinOps Policy Configuration
# ============================================================

POLICY_TITLE = "EBS Volume Stopped"

CATEGORY = "EBS Volume Stopped"

SERVICE = "EBS"

# EC2 state that makes the attached EBS volume
# a candidate.
TARGET_INSTANCE_STATE = "stopped"


# ============================================================
# 4. Create AWS Clients
# ============================================================

def create_clients(region_name):

    ec2 = boto3.client(
        "ec2",
        region_name=region_name,
        config=AWS_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG
    )

    return (
        ec2,
        sts
    )


# ============================================================
# 5. Get Account ID
# ============================================================

def get_account_id(sts):

    return sts.get_caller_identity()["Account"]


# ============================================================
# 6. Fetch All Resources with Pagination
# ============================================================

def fetch_all_ebs_volumes(ec2):

    volumes = []

    paginator = ec2.get_paginator(
        "describe_volumes"
    )

    for page in paginator.paginate():

        volumes.extend(
            page.get(
                "Volumes",
                []
            )
        )

    return volumes


def fetch_all_ec2_instances(ec2):

    instances = []

    paginator = ec2.get_paginator(
        "describe_instances"
    )

    for page in paginator.paginate():

        for reservation in page.get(
            "Reservations",
            []
        ):

            instances.extend(
                reservation.get(
                    "Instances",
                    []
                )
            )

    return instances


# ============================================================
# 7. Fetch Additional AWS Data
# ============================================================

def get_resource_tags(
    resource
):

    tags = {}

    for tag in resource.get(
        "Tags",
        []
    ):

        key = tag.get("Key")
        value = tag.get("Value")

        if key:

            tags[key] = value

    return tags


def build_instance_map(
    instances
):

    instance_map = {}

    for instance in instances:

        instance_id = instance.get(
            "InstanceId"
        )

        if not instance_id:

            continue

        instance_map[
            instance_id
        ] = instance

    return instance_map


def get_volume_attachment(
    volume
):

    attachments = volume.get(
        "Attachments",
        []
    )

    if not attachments:

        return None

    # Normally an EBS volume is attached
    # to one EC2 instance.
    attachment = attachments[0]

    return {
        "instance_id": attachment.get(
            "InstanceId"
        ),
        "device": attachment.get(
            "Device"
        ),
        "attachment_state": attachment.get(
            "State"
        ),
        "delete_on_termination": attachment.get(
            "DeleteOnTermination"
        )
    }


def calculate_age_days(
    create_time
):

    if not create_time:

        return None

    if create_time.tzinfo is None:

        create_time = create_time.replace(
            tzinfo=timezone.utc
        )

    now = datetime.now(
        timezone.utc
    )

    return (
        now - create_time
    ).days


# ============================================================
# 8. Evaluate FinOps Policy
# ============================================================

def evaluate_volume(
    volume,
    instance_map,
    account_id,
    region
):

    volume_id = volume.get(
        "VolumeId"
    )

    volume_state = volume.get(
        "State"
    )

    volume_type = volume.get(
        "VolumeType"
    )

    size_gib = volume.get(
        "Size"
    )

    encrypted = volume.get(
        "Encrypted"
    )

    availability_zone = volume.get(
        "AvailabilityZone"
    )

    create_time = volume.get(
        "CreateTime"
    )

    snapshot_id = volume.get(
        "SnapshotId"
    )

    iops = volume.get(
        "Iops"
    )

    throughput = volume.get(
        "Throughput"
    )

    volume_tags = get_resource_tags(
        volume
    )

    # --------------------------------------------------------
    # Volume must be attached.
    # --------------------------------------------------------

    attachment = get_volume_attachment(
        volume
    )

    if not attachment:

        return None

    instance_id = attachment[
        "instance_id"
    ]

    if not instance_id:

        return None

    # --------------------------------------------------------
    # Find corresponding EC2 instance.
    # --------------------------------------------------------

    instance = instance_map.get(
        instance_id
    )

    if not instance:

        return {
            "candidate": False,
            "reason": (
                "EBS volume is attached to an "
                "instance ID that is no longer "
                "present in the current EC2 inventory."
            ),
            "account_id": account_id,
            "region": region,
            "volume_id": volume_id,
            "volume_state": volume_state,
            "volume_type": volume_type,
            "size_gib": size_gib,
            "encrypted": encrypted,
            "availability_zone": availability_zone,
            "create_time": create_time,
            "snapshot_id": snapshot_id,
            "iops": iops,
            "throughput": throughput,
            "attachment": attachment,
            "instance": None,
            "volume_tags": volume_tags
        }

    # --------------------------------------------------------
    # EC2 instance state.
    # --------------------------------------------------------

    instance_state = (
        instance.get(
            "State",
            {}
        ).get(
            "Name"
        )
    )

    instance_name = ""

    instance_tags = get_resource_tags(
        instance
    )

    if instance_tags.get(
        "Name"
    ):

        instance_name = instance_tags[
            "Name"
        ]

    # --------------------------------------------------------
    # Policy condition.
    # --------------------------------------------------------

    if instance_state == TARGET_INSTANCE_STATE:

        candidate = True

        reason = (
            "EBS volume is attached to an "
            "EC2 instance that is currently "
            "stopped."
        )

    else:

        candidate = False

        reason = (
            f"Attached EC2 instance state is "
            f"{instance_state}, not stopped."
        )

    # --------------------------------------------------------
    # Recommendation.
    # --------------------------------------------------------

    if candidate:

        recommendation = (
            "Review whether the stopped EC2 instance "
            "and its EBS volume are still required. "
            "If no longer required, take an appropriate "
            "backup/snapshot and delete the EBS volume "
            "after owner approval."
        )

    else:

        recommendation = (
            "No EBS Volume Stopped candidate."
        )

    return {
        "candidate": candidate,
        "reason": reason,
        "recommendation": recommendation,
        "account_id": account_id,
        "region": region,
        "volume_id": volume_id,
        "volume_state": volume_state,
        "volume_type": volume_type,
        "size_gib": size_gib,
        "encrypted": encrypted,
        "availability_zone": availability_zone,
        "create_time": create_time,
        "snapshot_id": snapshot_id,
        "iops": iops,
        "throughput": throughput,
        "attachment": attachment,
        "instance": instance,
        "instance_id": instance_id,
        "instance_name": instance_name,
        "instance_state": instance_state,
        "volume_tags": volume_tags,
        "instance_tags": instance_tags
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

    volume_id = evaluation[
        "volume_id"
    ]

    volume_state = evaluation[
        "volume_state"
    ]

    volume_type = evaluation[
        "volume_type"
    ]

    size_gib = evaluation[
        "size_gib"
    ]

    encrypted = evaluation[
        "encrypted"
    ]

    availability_zone = evaluation[
        "availability_zone"
    ]

    create_time = evaluation[
        "create_time"
    ]

    snapshot_id = evaluation[
        "snapshot_id"
    ]

    iops = evaluation[
        "iops"
    ]

    throughput = evaluation[
        "throughput"
    ]

    attachment = evaluation[
        "attachment"
    ]

    instance_id = evaluation[
        "instance_id"
    ]

    instance_name = evaluation[
        "instance_name"
    ]

    instance_state = evaluation[
        "instance_state"
    ]

    volume_tags = evaluation[
        "volume_tags"
    ]

    instance_tags = evaluation[
        "instance_tags"
    ]

    candidate = evaluation[
        "candidate"
    ]

    reason = evaluation[
        "reason"
    ]

    recommendation = evaluation[
        "recommendation"
    ]

    # --------------------------------------------------------
    # Created date / age
    # --------------------------------------------------------

    created_date_text = ""

    if create_time:

        created_date_text = (
            create_time.strftime(
                "%d-%m-%Y"
            )
        )

    age_days = calculate_age_days(
        create_time
    )

    # --------------------------------------------------------
    # Attachment details
    # --------------------------------------------------------

    device = attachment.get(
        "device"
    )

    attachment_state = attachment.get(
        "attachment_state"
    )

    delete_on_termination = (
        attachment.get(
            "delete_on_termination"
        )
    )

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    description = (
        f"VolumeType: {volume_type} | "
        f"SizeGB: {size_gib} | "
        f"VolumeState: {volume_state} | "
        f"Encrypted: "
        f"{'Yes' if encrypted else 'No'} | "
        f"AvailabilityZone: "
        f"{availability_zone} | "
        f"CreatedDate: {created_date_text} | "
        f"AgeDays: {age_days} | "
        f"SnapshotId: "
        f"{snapshot_id or 'None'} | "
        f"IOPS: {iops} | "
        f"ThroughputMBps: "
        f"{throughput} | "
        f"InstanceId: {instance_id} | "
        f"InstanceName: "
        f"{instance_name or 'Unnamed'} | "
        f"InstanceState: {instance_state} | "
        f"Device: {device or 'None'} | "
        f"AttachmentState: "
        f"{attachment_state or 'None'} | "
        f"DeleteOnTermination: "
        f"{delete_on_termination} | "
        f"VolumeTags: {volume_tags} | "
        f"InstanceTags: {instance_tags} | "
        f"Evaluation: {reason} | "
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
        "status": (
            "Pending for Review"
            if candidate
            else "Not a Candidate"
        ),
        "areaPath": "AWS Cost Optimization",
        "tags": "",
        "commentCount": 0,
        "accountId": account_id,
        "region": region,
        "resourceNameOrId": volume_id,
        "resourceId": volume_id,
        "resourceArn": "",
        "service": SERVICE,
        "type": "EBS Volume",
        "policy": POLICY_TITLE,
        "effortLevel": "Medium",
        "message": "EBS volume is attached to a stopped instance.",
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

    print("=" * 80)
    print("AWS FinOps Policy Scan")
    print("=" * 80)

    print(
        f"Policy : {POLICY_TITLE}"
    )

    print(
        f"Service: {SERVICE}"
    )

    print(
        f"Region : {REGION}"
    )

    print("=" * 80)

    # --------------------------------------------------------
    # Create clients
    # --------------------------------------------------------

    (
        ec2,
        sts
    ) = create_clients(
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
    # Fetch EBS volumes
    # --------------------------------------------------------

    print(
        "Fetching EBS volumes..."
    )

    volumes = fetch_all_ebs_volumes(
        ec2
    )

    print(
        f"EBS volumes scanned: "
        f"{len(volumes)}"
    )

    # --------------------------------------------------------
    # Fetch EC2 instances
    # --------------------------------------------------------

    print(
        "Fetching EC2 instances..."
    )

    instances = fetch_all_ec2_instances(
        ec2
    )

    print(
        f"EC2 instances scanned: "
        f"{len(instances)}"
    )

    instance_map = build_instance_map(
        instances
    )

    # --------------------------------------------------------
    # Evaluate volumes
    # --------------------------------------------------------

    findings = []

    candidate_count = 0

    stopped_instance_count = 0

    for volume in volumes:

        evaluation = evaluate_volume(
            volume,
            instance_map,
            account_id,
            REGION
        )

        # Skip volumes that are not attached.
        if evaluation is None:

            continue

        if evaluation[
            "candidate"
        ]:

            candidate_count += 1

            stopped_instance_count += 1

        finding = build_finding(
            evaluation
        )

        # ----------------------------------------------------
        # Only output actual policy candidates.
        # ----------------------------------------------------

        if evaluation[
            "candidate"
        ]:

            findings.append(
                finding
            )

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
        scan_end_time -
        scan_start_time
    ).total_seconds()

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 80)
    print("SCAN SUMMARY")
    print("=" * 80)

    print(
        f"Account ID              : "
        f"{account_id}"
    )

    print(
        f"Region                  : "
        f"{REGION}"
    )

    print(
        f"EBS Volumes Scanned     : "
        f"{len(volumes)}"
    )

    print(
        f"EC2 Instances Scanned   : "
        f"{len(instances)}"
    )

    print(
        f"Stopped EBS Candidates  : "
        f"{candidate_count}"
    )

    print(
        f"Scan Duration           : "
        f"{scan_duration:.2f} seconds"
    )

    print(
        f"Excel Output            : "
        f"{OUTPUT_FILE}"
    )

    print("=" * 80)


if __name__ == "__main__":
    main()