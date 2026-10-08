# ============================================================
# AWS FinOps Policy
# Policy: Disk Over provisioned
# Service: EBS
# ============================================================


# ============================================================
# 1. Imports
# ============================================================

import boto3
import pandas as pd

from datetime import datetime, timezone, timedelta
from botocore.config import Config


# ============================================================
# 2. AWS Configuration
# ============================================================

REGION = "us-east-1"

OUTPUT_FILE = (
    "ebs_disk_over_provisioned.xlsx"
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

POLICY_TITLE = "Disk Over provisioned"

CATEGORY = "Disk Over provisioned"

SERVICE = "EBS"

# Number of days of CloudWatch data to examine.
METRIC_LOOKBACK_DAYS = 14

# Percentage of provisioned storage that should be considered
# excessive before creating a candidate.
OVER_PROVISIONED_THRESHOLD_PERCENT = 30

# Minimum free space to retain on the resized volume.
RECOMMENDED_FREE_SPACE_PERCENT = 20

# Minimum recommended volume size.
MIN_RECOMMENDED_SIZE_GIB = 10

# CloudWatch metric namespace.
CLOUDWATCH_NAMESPACE = "CWAgent"


# ============================================================
# 4. Create AWS Clients
# ============================================================

def create_clients(region_name):

    ec2 = boto3.client(
        "ec2",
        region_name=region_name,
        config=AWS_CONFIG
    )

    cloudwatch = boto3.client(
        "cloudwatch",
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
        cloudwatch,
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

    pages = paginator.paginate()

    for page in pages:

        volumes.extend(
            page.get(
                "Volumes",
                []
            )
        )

    return volumes


# ============================================================
# 7. Fetch Additional AWS Data / Metrics
# ============================================================

def get_volume_tags(volume):

    tags = {}

    for tag in volume.get(
        "Tags",
        []
    ):

        key = tag.get("Key")
        value = tag.get("Value")

        if key:

            tags[key] = value

    return tags


def get_attached_instance_id(
    volume
):

    attachments = volume.get(
        "Attachments",
        []
    )

    for attachment in attachments:

        instance_id = attachment.get(
            "InstanceId"
        )

        if instance_id:

            return instance_id

    return None


def get_volume_mount_information(
    volume
):

    """
    Returns attachment information.

    EBS itself knows the volume and attachment,
    but not the guest filesystem mount point.
    """

    attachments = volume.get(
        "Attachments",
        []
    )

    if not attachments:

        return {
            "attached": False,
            "instance_id": None,
            "device": None
        }

    attachment = attachments[0]

    return {
        "attached": True,
        "instance_id": attachment.get(
            "InstanceId"
        ),
        "device": attachment.get(
            "Device"
        )
    }


def get_cloudwatch_used_space(
    cloudwatch,
    instance_id,
    device
):

    """
    Attempts to retrieve filesystem usage through
    CloudWatch Agent.

    Important:
    EC2/EBS APIs do NOT provide filesystem-used GiB.

    CloudWatch Agent must be installed and configured
    on the instance for this metric to exist.

    Expected custom metric examples:

        LogicalDisk % Committed Bytes In Use

    or

        disk_used_percent

    The exact metric/dimension depends on the
    CloudWatch Agent configuration.
    """

    if not instance_id:

        return None

    if not device:

        return None

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time -
        timedelta(
            days=METRIC_LOOKBACK_DAYS
        )
    )

    # --------------------------------------------------------
    # First attempt:
    # Linux CloudWatch Agent disk_used_percent
    # --------------------------------------------------------

    try:

        response = cloudwatch.get_metric_statistics(
            Namespace=CLOUDWATCH_NAMESPACE,
            MetricName="disk_used_percent",
            Dimensions=[
                {
                    "Name": "InstanceId",
                    "Value": instance_id
                }
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,
            Statistics=[
                "Maximum"
            ]
        )

        datapoints = response.get(
            "Datapoints",
            []
        )

        if datapoints:

            latest = max(
                datapoints,
                key=lambda x: x.get(
                    "Timestamp"
                )
            )

            used_percent = latest.get(
                "Maximum"
            )

            if used_percent is not None:

                return {
                    "used_percent": float(
                        used_percent
                    ),
                    "metric_name": (
                        "disk_used_percent"
                    )
                }

    except Exception as error:

        print(
            f"CloudWatch metric lookup failed "
            f"for {instance_id}: {error}"
        )

    return None


def calculate_used_gib(
    provisioned_gib,
    used_percent
):

    if (
        provisioned_gib is None
        or used_percent is None
    ):

        return None

    return (
        provisioned_gib *
        used_percent /
        100
    )


def calculate_recommended_size(
    used_gib
):

    if used_gib is None:

        return None

    # Keep the configured free-space percentage.
    required_size = (
        used_gib /
        (
            1 -
            (
                RECOMMENDED_FREE_SPACE_PERCENT
                / 100
            )
        )
    )

    # Round up to the next 5 GiB.
    recommended_size = (
        int(
            (
                required_size + 4
            ) // 5
        ) * 5
    )

    recommended_size = max(
        recommended_size,
        MIN_RECOMMENDED_SIZE_GIB
    )

    return recommended_size


# ============================================================
# 8. Evaluate FinOps Policy
# ============================================================

def evaluate_volume(
    volume,
    cloudwatch,
    account_id,
    region
):

    volume_id = volume.get(
        "VolumeId"
    )

    provisioned_gib = volume.get(
        "Size"
    )

    volume_type = volume.get(
        "VolumeType"
    )

    state = volume.get(
        "State"
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

    tags = get_volume_tags(
        volume
    )

    mount_info = (
        get_volume_mount_information(
            volume
        )
    )

    instance_id = mount_info[
        "instance_id"
    ]

    device = mount_info[
        "device"
    ]

    # --------------------------------------------------------
    # We need an attached volume because filesystem
    # utilization comes from the guest OS.
    # --------------------------------------------------------

    if not mount_info["attached"]:

        return {
            "candidate": False,
            "reason": (
                "Volume is not attached. "
                "Filesystem utilization cannot "
                "be determined from CloudWatch Agent."
            ),
            "volume_id": volume_id,
            "account_id": account_id,
            "region": region,
            "provisioned_gib": provisioned_gib,
            "used_gib": None,
            "used_percent": None,
            "recommended_size_gib": None,
            "potential_reduction_gib": None,
            "volume_type": volume_type,
            "state": state,
            "encrypted": encrypted,
            "availability_zone": availability_zone,
            "create_time": create_time,
            "tags": tags,
            "instance_id": None,
            "device": None,
            "metric_name": None
        }

    # --------------------------------------------------------
    # Fetch utilization metric
    # --------------------------------------------------------

    metric_result = (
        get_cloudwatch_used_space(
            cloudwatch,
            instance_id,
            device
        )
    )

    if not metric_result:

        return {
            "candidate": False,
            "reason": (
                "Filesystem utilization metric "
                "is not available."
            ),
            "volume_id": volume_id,
            "account_id": account_id,
            "region": region,
            "provisioned_gib": provisioned_gib,
            "used_gib": None,
            "used_percent": None,
            "recommended_size_gib": None,
            "potential_reduction_gib": None,
            "volume_type": volume_type,
            "state": state,
            "encrypted": encrypted,
            "availability_zone": availability_zone,
            "create_time": create_time,
            "tags": tags,
            "instance_id": instance_id,
            "device": device,
            "metric_name": None
        }

    used_percent = (
        metric_result[
            "used_percent"
        ]
    )

    metric_name = (
        metric_result[
            "metric_name"
        ]
    )

    used_gib = calculate_used_gib(
        provisioned_gib,
        used_percent
    )

    recommended_size_gib = (
        calculate_recommended_size(
            used_gib
        )
    )

    if recommended_size_gib is None:

        return {
            "candidate": False,
            "reason": (
                "Unable to calculate "
                "recommended size."
            ),
            "volume_id": volume_id,
            "account_id": account_id,
            "region": region,
            "provisioned_gib": provisioned_gib,
            "used_gib": used_gib,
            "used_percent": used_percent,
            "recommended_size_gib": None,
            "potential_reduction_gib": None,
            "volume_type": volume_type,
            "state": state,
            "encrypted": encrypted,
            "availability_zone": availability_zone,
            "create_time": create_time,
            "tags": tags,
            "instance_id": instance_id,
            "device": device,
            "metric_name": metric_name
        }

    potential_reduction_gib = (
        provisioned_gib -
        recommended_size_gib
    )

    if potential_reduction_gib <= 0:

        candidate = False

        reason = (
            "Current provisioned size is "
            "already appropriate."
        )

    else:

        reduction_percent = (
            potential_reduction_gib /
            provisioned_gib *
            100
        )

        if (
            reduction_percent >=
            OVER_PROVISIONED_THRESHOLD_PERCENT
        ):

            candidate = True

            reason = (
                "Volume is over-provisioned."
            )

        else:

            candidate = False

            reason = (
                "Potential size reduction is "
                "below the configured threshold."
            )

    return {
        "candidate": candidate,
        "reason": reason,
        "volume_id": volume_id,
        "account_id": account_id,
        "region": region,
        "provisioned_gib": provisioned_gib,
        "used_gib": used_gib,
        "used_percent": used_percent,
        "recommended_size_gib": recommended_size_gib,
        "potential_reduction_gib": potential_reduction_gib,
        "volume_type": volume_type,
        "state": state,
        "encrypted": encrypted,
        "availability_zone": availability_zone,
        "create_time": create_time,
        "tags": tags,
        "instance_id": instance_id,
        "device": device,
        "metric_name": metric_name
    }


# ============================================================
# 9. Build FinOps Finding
# ============================================================

def build_finding(
    evaluation
):

    volume_id = evaluation[
        "volume_id"
    ]

    account_id = evaluation[
        "account_id"
    ]

    region = evaluation[
        "region"
    ]

    provisioned_gib = evaluation[
        "provisioned_gib"
    ]

    used_gib = evaluation[
        "used_gib"
    ]

    used_percent = evaluation[
        "used_percent"
    ]

    recommended_size_gib = evaluation[
        "recommended_size_gib"
    ]

    potential_reduction_gib = evaluation[
        "potential_reduction_gib"
    ]

    volume_type = evaluation[
        "volume_type"
    ]

    state = evaluation[
        "state"
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

    tags = evaluation[
        "tags"
    ]

    instance_id = evaluation[
        "instance_id"
    ]

    device = evaluation[
        "device"
    ]

    metric_name = evaluation[
        "metric_name"
    ]

    candidate = evaluation[
        "candidate"
    ]

    reason = evaluation[
        "reason"
    ]

    # --------------------------------------------------------
    # Date
    # --------------------------------------------------------

    created_date_text = ""

    if create_time:

        created_date_text = (
            create_time.strftime(
                "%d-%m-%Y"
            )
        )

    # --------------------------------------------------------
    # Numerical formatting
    # --------------------------------------------------------

    if used_gib is not None:

        used_gib_text = (
            f"{used_gib:.2f}"
        )

    else:

        used_gib_text = (
            "Not Available"
        )

    if used_percent is not None:

        used_percent_text = (
            f"{used_percent:.2f}%"
        )

    else:

        used_percent_text = (
            "Not Available"
        )

    if recommended_size_gib is not None:

        recommended_size_text = (
            f"{recommended_size_gib} GiB"
        )

    else:

        recommended_size_text = (
            "Not Available"
        )

    if potential_reduction_gib is not None:

        reduction_text = (
            f"{potential_reduction_gib} GiB"
        )

    else:

        reduction_text = (
            "Not Available"
        )

    # --------------------------------------------------------
    # Recommendation
    # --------------------------------------------------------

    if candidate:

        recommendation = (
            f"Reduce EBS volume from "
            f"{provisioned_gib} GiB to approximately "
            f"{recommended_size_gib} GiB based on "
            f"observed filesystem utilization. "
            f"Potential reduction: "
            f"{potential_reduction_gib} GiB."
        )

    else:

        recommendation = reason

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    description = (
        f"ProvisionedSizeGB: {provisioned_gib} | "
        f"ActualUsedGB: {used_gib_text} | "
        f"UsedPercent: {used_percent_text} | "
        f"RecommendedSizeGB: "
        f"{recommended_size_text} | "
        f"PotentialReductionGB: "
        f"{reduction_text} | "
        f"VolumeType: {volume_type} | "
        f"State: {state} | "
        f"Encrypted: "
        f"{'Yes' if encrypted else 'No'} | "
        f"AvailabilityZone: "
        f"{availability_zone} | "
        f"CreatedDate: {created_date_text} | "
        f"AttachedInstance: "
        f"{instance_id or 'None'} | "
        f"Device: {device or 'None'} | "
        f"Metric: {metric_name or 'Not Available'} | "
        f"Tags: {tags} | "
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
        "message": "EBS volume is over-provisioned.",
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
        f"Metric Lookback: "
        f"{METRIC_LOOKBACK_DAYS} days"
    )

    print("=" * 80)

    # --------------------------------------------------------
    # Create clients
    # --------------------------------------------------------

    (
        ec2,
        cloudwatch,
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
    # Evaluate volumes
    # --------------------------------------------------------

    findings = []

    candidate_count = 0

    metric_missing_count = 0

    unattached_count = 0

    for volume in volumes:

        evaluation = evaluate_volume(
            volume,
            cloudwatch,
            account_id,
            REGION
        )

        if not evaluation:
            continue

        if (
            evaluation[
                "used_gib"
            ] is None
        ):

            if not evaluation[
                "instance_id"
            ]:

                unattached_count += 1

            else:

                metric_missing_count += 1

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
        f"FinOps Candidates       : "
        f"{candidate_count}"
    )

    print(
        f"Unattached Volumes      : "
        f"{unattached_count}"
    )

    print(
        f"Missing Utilization     : "
        f"{metric_missing_count}"
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