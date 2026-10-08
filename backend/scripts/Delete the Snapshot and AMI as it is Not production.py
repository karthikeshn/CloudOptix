# ============================================================
# AWS FinOps Policy
# Policy: Delete the Snapshot and AMI as it is Not production
# Service: EBS Snapshot
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
    "delete_snapshot_and_ami_non_production.xlsx"
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

POLICY_TITLE = (
    "Delete the Snapshot and AMI as it is Not production"
)

CATEGORY = (
    "Delete the Snapshot and AMI as it is Not production"
)

SERVICE = "EBS Snapshot"

SNAPSHOT_AGE_THRESHOLD_DAYS = 30


# Keywords used to classify resources as non-production.
# This classification is based on resource names/tags.
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
    "nonproduction",
    "non-production",
    "sandbox",
    "perf",
    "performance"
]


# Keywords that explicitly indicate production.
PRODUCTION_KEYWORDS = [
    "prod",
    "production"
]


# ============================================================
# 4. Create AWS Clients
# ============================================================

def create_clients(region_name):

    ec2 = boto3.client(
        "ec2",
        region_name=region_name,
        config=AWS_CONFIG
    )

    autoscaling = boto3.client(
        "autoscaling",
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
        autoscaling,
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

def fetch_all_ebs_snapshots(ec2):

    snapshots = []

    paginator = ec2.get_paginator(
        "describe_snapshots"
    )

    # OwnerIds=["self"] prevents scanning public/shared
    # snapshots that do not belong to the account.
    pages = paginator.paginate(
        OwnerIds=["self"]
    )

    for page in pages:

        snapshots.extend(
            page.get(
                "Snapshots",
                []
            )
        )

    return snapshots


def fetch_all_ebs_volumes(ec2):

    volumes = []

    paginator = ec2.get_paginator(
        "describe_volumes"
    )

    pages = paginator.paginate()

    for page in pages:

        volumes.extend(
            page.get(
                "Volumes",
                []
            )
        )

    return volumes


def fetch_all_images(ec2):

    images = []

    paginator = ec2.get_paginator(
        "describe_images"
    )

    pages = paginator.paginate(
        Owners=["self"]
    )

    for page in pages:

        images.extend(
            page.get(
                "Images",
                []
            )
        )

    return images


def fetch_all_instances(ec2):

    instances = []

    paginator = ec2.get_paginator(
        "describe_instances"
    )

    pages = paginator.paginate()

    for page in pages:

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


def fetch_all_auto_scaling_groups(
    autoscaling
):

    groups = []

    paginator = autoscaling.get_paginator(
        "describe_auto_scaling_groups"
    )

    pages = paginator.paginate()

    for page in pages:

        groups.extend(
            page.get(
                "AutoScalingGroups",
                []
            )
        )

    return groups


# ============================================================
# 7. Fetch Additional AWS Data / Metrics
# ============================================================

def convert_tags_to_dict(
    tags
):

    tag_dict = {}

    for tag in tags or []:

        key = tag.get("Key")
        value = tag.get("Value")

        if key:
            tag_dict[key] = value

    return tag_dict


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


def build_volume_map(
    volumes
):

    volume_map = {}

    for volume in volumes:

        volume_id = volume.get(
            "VolumeId"
        )

        if not volume_id:
            continue

        volume_map[
            volume_id
        ] = volume

    return volume_map


def build_instance_map(
    instances
):

    instance_map = {}

    for instance in instances:

        instance_id = instance.get(
            "InstanceId"
        )

        if instance_id:

            instance_map[
                instance_id
            ] = instance

    return instance_map


def build_ami_snapshot_map(
    images
):

    """
    Build:

        Snapshot ID
            ->
        AMI information

    An AMI can contain multiple EBS
    block-device mappings.
    """

    snapshot_map = {}

    for image in images:

        image_id = image.get(
            "ImageId"
        )

        image_name = image.get(
            "Name"
        )

        image_tags = convert_tags_to_dict(
            image.get(
                "Tags",
                []
            )
        )

        creation_date = image.get(
            "CreationDate"
        )

        block_device_mappings = (
            image.get(
                "BlockDeviceMappings",
                []
            )
        )

        for mapping in block_device_mappings:

            ebs = mapping.get(
                "Ebs"
            )

            if not ebs:
                continue

            snapshot_id = ebs.get(
                "SnapshotId"
            )

            if not snapshot_id:
                continue

            snapshot_map.setdefault(
                snapshot_id,
                []
            ).append(
                {
                    "ami_id": image_id,
                    "ami_name": image_name,
                    "ami_creation_date": (
                        creation_date
                    ),
                    "ami_tags": image_tags
                }
            )

    return snapshot_map


def build_asg_instance_map(
    auto_scaling_groups
):

    """
    Build:

        EC2 Instance ID
            ->
        Auto Scaling Group
    """

    instance_map = {}

    for group in auto_scaling_groups:

        group_name = group.get(
            "AutoScalingGroupName"
        )

        instances = group.get(
            "Instances",
            []
        )

        for instance in instances:

            instance_id = instance.get(
                "InstanceId"
            )

            if instance_id:

                instance_map[
                    instance_id
                ] = group_name

    return instance_map


def get_instance_ids_from_volume(
    volume
):

    instance_ids = []

    for attachment in volume.get(
        "Attachments",
        []
    ):

        instance_id = attachment.get(
            "InstanceId"
        )

        if instance_id:

            instance_ids.append(
                instance_id
            )

    return instance_ids


def find_source_instance(
    volume,
    instance_map
):

    instance_ids = (
        get_instance_ids_from_volume(
            volume
        )
    )

    for instance_id in instance_ids:

        instance = instance_map.get(
            instance_id
        )

        if instance:

            return instance

    return None


def determine_environment(
    snapshot,
    volume,
    ami_records,
    source_instance
):

    """
    Determine Production / Non-Production
    using names and tags.

    This intentionally uses multiple resource
    signals instead of relying only on the
    snapshot name.
    """

    signals = []

    # --------------------------------------------------------
    # Snapshot
    # --------------------------------------------------------

    snapshot_tags = convert_tags_to_dict(
        snapshot.get(
            "Tags",
            []
        )
    )

    signals.extend(
        [
            str(
                snapshot.get(
                    "Description"
                )
                or ""
            ),
            str(
                snapshot.get(
                    "SnapshotId"
                )
                or ""
            )
        ]
    )

    signals.extend(
        [
            str(value)
            for value in snapshot_tags.values()
        ]
    )

    # --------------------------------------------------------
    # Volume
    # --------------------------------------------------------

    if volume:

        signals.append(
            str(
                volume.get(
                    "VolumeId"
                )
                or ""
            )
        )

        signals.extend(
            [
                str(value)
                for value in convert_tags_to_dict(
                    volume.get(
                        "Tags",
                        []
                    )
                ).values()
            ]
        )

    # --------------------------------------------------------
    # Source EC2 instance
    # --------------------------------------------------------

    if source_instance:

        signals.append(
            str(
                source_instance.get(
                    "InstanceId"
                )
                or ""
            )
        )

        signals.append(
            str(
                source_instance.get(
                    "PrivateDnsName"
                )
                or ""
            )
        )

        signals.extend(
            [
                str(value)
                for value in convert_tags_to_dict(
                    source_instance.get(
                        "Tags",
                        []
                    )
                ).values()
            ]
        )

    # --------------------------------------------------------
    # AMI
    # --------------------------------------------------------

    for ami in ami_records:

        signals.append(
            str(
                ami.get(
                    "ami_id"
                )
                or ""
            )
        )

        signals.append(
            str(
                ami.get(
                    "ami_name"
                )
                or ""
            )
        )

        signals.extend(
            [
                str(value)
                for value in ami.get(
                    "ami_tags",
                    {}
                ).values()
            ]
        )

    combined_text = " ".join(
        signals
    ).lower()

    # --------------------------------------------------------
    # Production check
    # --------------------------------------------------------

    production_matches = [
        keyword
        for keyword in PRODUCTION_KEYWORDS
        if keyword in combined_text
    ]

    non_production_matches = [
        keyword
        for keyword in NON_PRODUCTION_KEYWORDS
        if keyword in combined_text
    ]

    # Explicit production signal wins.
    if production_matches:

        return (
            "Production",
            production_matches,
            non_production_matches
        )

    if non_production_matches:

        return (
            "Non-Production",
            production_matches,
            non_production_matches
        )

    return (
        "Unknown",
        production_matches,
        non_production_matches
    )


# ============================================================
# 8. Evaluate FinOps Policy
# ============================================================

def evaluate_snapshot(
    snapshot,
    volume_map,
    ami_snapshot_map,
    instance_map,
    asg_instance_map,
    account_id,
    region
):

    snapshot_id = snapshot.get(
        "SnapshotId"
    )

    state = snapshot.get(
        "State"
    )

    start_time = snapshot.get(
        "StartTime"
    )

    age_days = calculate_age_days(
        start_time
    )

    # --------------------------------------------------------
    # Only available snapshots
    # --------------------------------------------------------

    if state != "completed":
        return None

    # --------------------------------------------------------
    # Age > 30 days
    # --------------------------------------------------------

    if age_days is None:
        return None

    if age_days <= SNAPSHOT_AGE_THRESHOLD_DAYS:
        return None

    # --------------------------------------------------------
    # Snapshot details
    # --------------------------------------------------------

    volume_id = snapshot.get(
        "VolumeId"
    )

    volume = volume_map.get(
        volume_id
    )

    volume_tags = {}

    if volume:

        volume_tags = convert_tags_to_dict(
            volume.get(
                "Tags",
                []
            )
        )

    # --------------------------------------------------------
    # AMI association
    # --------------------------------------------------------

    ami_records = ami_snapshot_map.get(
        snapshot_id,
        []
    )

    ami_ids = [
        ami.get(
            "ami_id"
        )
        for ami in ami_records
        if ami.get(
            "ami_id"
        )
    ]

    ami_names = [
        ami.get(
            "ami_name"
        )
        for ami in ami_records
        if ami.get(
            "ami_name"
        )
    ]

    # --------------------------------------------------------
    # Source EC2 instance
    # --------------------------------------------------------

    source_instance = None

    if volume:

        source_instance = find_source_instance(
            volume,
            instance_map
        )

    source_instance_id = None

    if source_instance:

        source_instance_id = (
            source_instance.get(
                "InstanceId"
            )
        )

    # --------------------------------------------------------
    # Auto Scaling Group
    # --------------------------------------------------------

    asg_name = None

    if source_instance_id:

        asg_name = asg_instance_map.get(
            source_instance_id
        )

    is_asg_resource = (
        asg_name is not None
    )

    # --------------------------------------------------------
    # Environment
    # --------------------------------------------------------

    (
        environment,
        production_matches,
        non_production_matches
    ) = determine_environment(
        snapshot,
        volume,
        ami_records,
        source_instance
    )

    # --------------------------------------------------------
    # Policy result
    # --------------------------------------------------------

    if is_asg_resource:

        recommendation = (
            "Excluded from optimization because "
            "the source EC2 instance is associated "
            "with an Auto Scaling Group."
        )

        candidate = False

    elif environment == "Non-Production":

        recommendation = (
            "Delete the non-production EBS snapshot. "
            "If the snapshot is associated with an "
            "AMI, review and deregister the AMI before "
            "deleting the snapshot."
        )

        candidate = True

    elif environment == "Production":

        recommendation = (
            "Archive the production EBS snapshot "
            "instead of deleting it."
        )

        candidate = True

    else:

        recommendation = (
            "Environment could not be confidently "
            "identified. Review manually before "
            "deleting or archiving the snapshot."
        )

        candidate = False

    # --------------------------------------------------------
    # Return evaluation
    # --------------------------------------------------------

    return {
        "account_id": account_id,
        "region": region,
        "snapshot_id": snapshot_id,
        "snapshot_state": state,
        "created_date": start_time,
        "age_days": age_days,
        "size_gb": snapshot.get(
            "VolumeSize"
        ),
        "encrypted": snapshot.get(
            "Encrypted"
        ),
        "description": snapshot.get(
            "Description"
        ),
        "volume_id": volume_id,
        "volume": volume,
        "volume_tags": volume_tags,
        "ami_records": ami_records,
        "ami_ids": ami_ids,
        "ami_names": ami_names,
        "source_instance_id": source_instance_id,
        "source_instance": source_instance,
        "asg_name": asg_name,
        "is_asg_resource": is_asg_resource,
        "environment": environment,
        "production_matches": production_matches,
        "non_production_matches": (
            non_production_matches
        ),
        "candidate": candidate,
        "recommendation": recommendation
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

    snapshot_id = evaluation[
        "snapshot_id"
    ]

    snapshot_state = evaluation[
        "snapshot_state"
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

    volume_id = evaluation[
        "volume_id"
    ]

    ami_ids = evaluation[
        "ami_ids"
    ]

    ami_names = evaluation[
        "ami_names"
    ]

    source_instance_id = evaluation[
        "source_instance_id"
    ]

    asg_name = evaluation[
        "asg_name"
    ]

    is_asg_resource = evaluation[
        "is_asg_resource"
    ]

    environment = evaluation[
        "environment"
    ]

    production_matches = evaluation[
        "production_matches"
    ]

    non_production_matches = evaluation[
        "non_production_matches"
    ]

    recommendation = evaluation[
        "recommendation"
    ]

    volume_tags = evaluation[
        "volume_tags"
    ]

    # --------------------------------------------------------
    # AMI information
    # --------------------------------------------------------

    ami_id_text = (
        ", ".join(ami_ids)
        if ami_ids
        else "None"
    )

    ami_name_text = (
        ", ".join(
            [
                str(name)
                for name in ami_names
                if name
            ]
        )
        if ami_names
        else "None"
    )

    # --------------------------------------------------------
    # Created date
    # --------------------------------------------------------

    created_date_text = ""

    if created_date:

        created_date_text = (
            created_date.strftime(
                "%d-%m-%Y"
            )
        )

    # --------------------------------------------------------
    # Classification signals
    # --------------------------------------------------------

    production_signal_text = (
        ", ".join(
            production_matches
        )
        if production_matches
        else "None"
    )

    non_production_signal_text = (
        ", ".join(
            non_production_matches
        )
        if non_production_matches
        else "None"
    )

    # --------------------------------------------------------
    # ASG status
    # --------------------------------------------------------

    asg_status = (
        f"Yes ({asg_name})"
        if is_asg_resource
        else "No"
    )

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    description = (
        f"SnapshotType: EBS Snapshot | "
        f"State: {snapshot_state} | "
        f"CreatedDate: {created_date_text} | "
        f"AgeDays: {age_days} | "
        f"SizeGB: {size_gb} | "
        f"Encrypted: "
        f"{'Yes' if encrypted else 'No'} | "
        f"SourceVolume: {volume_id or 'Unknown'} | "
        f"AMIAssociated: "
        f"{'Yes' if ami_ids else 'No'} | "
        f"AMIIds: {ami_id_text} | "
        f"AMINames: {ami_name_text} | "
        f"SourceInstance: "
        f"{source_instance_id or 'Unknown'} | "
        f"Environment: {environment} | "
        f"ProductionSignals: "
        f"{production_signal_text} | "
        f"NonProductionSignals: "
        f"{non_production_signal_text} | "
        f"AutoScalingGroup: {asg_status} | "
        f"VolumeTags: {volume_tags} | "
        f"Recommendation: {recommendation}"
    )

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    if is_asg_resource:

        status = "Excluded"

    elif environment == "Unknown":

        status = "Pending for Review"

    else:

        status = "Pending for Review"

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
        "status": status,
        "areaPath": "AWS Cost Optimization",
        "tags": "",
        "commentCount": 0,
        "accountId": account_id,
        "region": region,
        "resourceNameOrId": snapshot_id,
        "resourceId": snapshot_id,
        "resourceArn": "",
        "service": SERVICE,
        "type": "EBS Snapshot",
        "policy": POLICY_TITLE,
        "effortLevel": "Medium",
        "message": "Review the non-production snapshot.",
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

    print(
        f"Age Threshold: "
        f"{SNAPSHOT_AGE_THRESHOLD_DAYS} days"
    )

    print("=" * 80)

    # --------------------------------------------------------
    # Create clients
    # --------------------------------------------------------

    (
        ec2,
        autoscaling,
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
    # Fetch snapshots
    # --------------------------------------------------------

    print(
        "Fetching EBS snapshots..."
    )

    snapshots = fetch_all_ebs_snapshots(
        ec2
    )

    print(
        f"EBS snapshots scanned: "
        f"{len(snapshots)}"
    )

    # --------------------------------------------------------
    # Fetch volumes
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
    # Fetch AMIs
    # --------------------------------------------------------

    print(
        "Fetching AMIs..."
    )

    images = fetch_all_images(
        ec2
    )

    print(
        f"AMIs scanned: "
        f"{len(images)}"
    )

    # --------------------------------------------------------
    # Fetch EC2 instances
    # --------------------------------------------------------

    print(
        "Fetching EC2 instances..."
    )

    instances = fetch_all_instances(
        ec2
    )

    print(
        f"EC2 instances scanned: "
        f"{len(instances)}"
    )

    # --------------------------------------------------------
    # Fetch Auto Scaling Groups
    # --------------------------------------------------------

    print(
        "Fetching Auto Scaling Groups..."
    )

    auto_scaling_groups = (
        fetch_all_auto_scaling_groups(
            autoscaling
        )
    )

    print(
        f"Auto Scaling Groups scanned: "
        f"{len(auto_scaling_groups)}"
    )

    # --------------------------------------------------------
    # Build lookup maps
    # --------------------------------------------------------

    volume_map = build_volume_map(
        volumes
    )

    instance_map = build_instance_map(
        instances
    )

    ami_snapshot_map = (
        build_ami_snapshot_map(
            images
        )
    )

    asg_instance_map = (
        build_asg_instance_map(
            auto_scaling_groups
        )
    )

    # --------------------------------------------------------
    # Evaluate snapshots
    # --------------------------------------------------------

    findings = []

    candidate_count = 0

    excluded_asg_count = 0

    unknown_environment_count = 0

    non_production_count = 0

    production_count = 0

    for snapshot in snapshots:

        evaluation = evaluate_snapshot(
            snapshot,
            volume_map,
            ami_snapshot_map,
            instance_map,
            asg_instance_map,
            account_id,
            REGION
        )

        if not evaluation:
            continue

        if evaluation[
            "is_asg_resource"
        ]:

            excluded_asg_count += 1

        if evaluation[
            "environment"
        ] == "Unknown":

            unknown_environment_count += 1

        elif evaluation[
            "environment"
        ] == "Non-Production":

            non_production_count += 1

        elif evaluation[
            "environment"
        ] == "Production":

            production_count += 1

        if evaluation[
            "candidate"
        ]:

            candidate_count += 1

        finding = build_finding(
            evaluation
        )

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
        scan_end_time - scan_start_time
    ).total_seconds()

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 80)
    print("SCAN SUMMARY")
    print("=" * 80)

    print(
        f"Account ID                 : "
        f"{account_id}"
    )

    print(
        f"Region                     : "
        f"{REGION}"
    )

    print(
        f"EBS Snapshots Scanned      : "
        f"{len(snapshots)}"
    )

    print(
        f"EBS Volumes Scanned        : "
        f"{len(volumes)}"
    )

    print(
        f"AMIs Scanned                : "
        f"{len(images)}"
    )

    print(
        f"EC2 Instances Scanned      : "
        f"{len(instances)}"
    )

    print(
        f"Auto Scaling Groups Scanned: "
        f"{len(auto_scaling_groups)}"
    )

    print(
        f"Non-Production Candidates  : "
        f"{non_production_count}"
    )

    print(
        f"Production Candidates      : "
        f"{production_count}"
    )

    print(
        f"ASG Excluded                : "
        f"{excluded_asg_count}"
    )

    print(
        f"Unknown Environment         : "
        f"{unknown_environment_count}"
    )

    print(
        f"Total FinOps Candidates     : "
        f"{candidate_count}"
    )

    print(
        f"Scan Duration               : "
        f"{scan_duration:.2f} seconds"
    )

    print(
        f"Excel Output                : "
        f"{OUTPUT_FILE}"
    )

    print("=" * 80)


if __name__ == "__main__":
    main()