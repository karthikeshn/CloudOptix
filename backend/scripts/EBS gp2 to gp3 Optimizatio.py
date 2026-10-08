# ============================================================
# AWS FinOps Policy
# Policy: EBS gp2 to gp3 Optimization
# Service: EBS
# ============================================================


# ============================================================
# 1. Imports
# ============================================================

import boto3
import pandas as pd
import sys
import os

# Import our modular pricing logic
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from pricing_rules import ebs_gp2_to_gp3_pricing
except ImportError:
    ebs_gp2_to_gp3_pricing = None

from datetime import datetime, timezone
from botocore.config import Config


# ============================================================
# 2. AWS Configuration
# ============================================================

REGION = "us-east-1"

OUTPUT_FILE = (
    "ebs_gp2_to_gp3_optimization.xlsx"
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
    "EBS gp2 to gp3 Optimization"
)

CATEGORY = (
    "EBS gp2 to gp3 Optimization"
)

SERVICE = "EBS"

SOURCE_VOLUME_TYPE = "gp2"

TARGET_VOLUME_TYPE = "gp3"


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


# ============================================================
# 7. Fetch Additional AWS Data
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


def get_attachment_details(
    volume
):

    attachments = volume.get(
        "Attachments",
        []
    )

    if not attachments:

        return {
            "attached": False,
            "instance_id": None,
            "device": None,
            "instance_state": None
        }

    attachment = attachments[0]

    return {
        "attached": True,
        "instance_id": attachment.get(
            "InstanceId"
        ),
        "device": attachment.get(
            "Device"
        ),
        "instance_state": attachment.get(
            "State"
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
    account_id,
    region
):

    volume_id = volume.get(
        "VolumeId"
    )

    volume_type = volume.get(
        "VolumeType"
    )

    size_gib = volume.get(
        "Size"
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

    snapshot_id = volume.get(
        "SnapshotId"
    )

    iops = volume.get(
        "Iops"
    )

    throughput = volume.get(
        "Throughput"
    )

    tags = get_volume_tags(
        volume
    )

    attachment = (
        get_attachment_details(
            volume
        )
    )

    # --------------------------------------------------------
    # Policy condition
    # --------------------------------------------------------

    if volume_type != SOURCE_VOLUME_TYPE:

        return None

    # --------------------------------------------------------
    # Determine recommendation status
    # --------------------------------------------------------

    if state != "in-use":

        candidate = False

        reason = (
            "EBS volume is gp2 but is not "
            "currently in-use."
        )

    elif not attachment["attached"]:

        candidate = False

        reason = (
            "EBS volume is gp2 but is not "
            "attached to an EC2 instance. "
            "Review separately as an unattached "
            "EBS volume."
        )

    else:

        candidate = True

        reason = (
            "EBS volume is using gp2 and can "
            "be evaluated for migration to gp3."
        )

    # --------------------------------------------------------
    # Recommendation
    # --------------------------------------------------------

    if candidate:

        recommendation = (
            f"Migrate EBS volume from "
            f"gp2 to gp3 while retaining "
            f"{size_gib} GiB capacity."
        )

    else:

        recommendation = (
            "Do not generate gp2-to-gp3 "
            "migration action automatically. "
            f"{reason}"
        )

    return {
        "candidate": candidate,
        "reason": reason,
        "recommendation": recommendation,
        "account_id": account_id,
        "region": region,
        "volume_id": volume_id,
        "volume_type": volume_type,
        "target_volume_type": TARGET_VOLUME_TYPE,
        "size_gib": size_gib,
        "state": state,
        "encrypted": encrypted,
        "availability_zone": availability_zone,
        "create_time": create_time,
        "snapshot_id": snapshot_id,
        "iops": iops,
        "throughput": throughput,
        "attachment": attachment,
        "tags": tags
    }


# ============================================================
# 9. Build FinOps Finding
# ============================================================

def build_finding(
    evaluation,
    pricing_data=None
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

    volume_type = evaluation[
        "volume_type"
    ]

    target_volume_type = evaluation[
        "target_volume_type"
    ]

    size_gib = evaluation[
        "size_gib"
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

    tags = evaluation[
        "tags"
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
    # Date
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
    # Attachment
    # --------------------------------------------------------

    instance_id = attachment[
        "instance_id"
    ]

    device = attachment[
        "device"
    ]

    attachment_state = attachment[
        "instance_state"
    ]

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    description = (
        f"VolumeType: {volume_type} | "
        f"RecommendedVolumeType: "
        f"{target_volume_type} | "
        f"SizeGB: {size_gib} | "
        f"State: {state} | "
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
        f"Attached: "
        f"{'Yes' if attachment['attached'] else 'No'} | "
        f"InstanceId: "
        f"{instance_id or 'None'} | "
        f"Device: "
        f"{device or 'None'} | "
        f"AttachmentState: "
        f"{attachment_state or 'None'} | "
        f"Tags: {tags} | "
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
        "message": "Migrate gp2 volume to gp3 to optimize costs.",
        "recommendation": recommendation,
        "description": description,
        "currentDailyCost": pricing_data.get("currentDailyCost", "To be updated") if pricing_data else "To be updated",
        "currentMonthlyCost": pricing_data.get("currentMonthlyCost", "To be updated") if pricing_data else "To be updated",
        "estimatedMonthlySavings": pricing_data.get("estimatedMonthlySavings", "To be updated") if pricing_data else "To be updated",
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
    # Execute Pricing Logic
    # --------------------------------------------------------
    evaluations = []
    
    for volume in volumes:
        evaluation = evaluate_volume(
            volume,
            account_id,
            REGION
        )

        # Not gp2
        if evaluation is None:
            continue
            
        gp2_count += 1

        # Statistics
        if evaluation["candidate"]:
            candidate_count += 1
        else:
            if evaluation["state"] != "in-use":
                not_in_use_count += 1
            elif not evaluation["attachment"]["attached"]:
                unattached_count += 1
                
        evaluations.append(evaluation)

    # Convert evaluations to the format expected by our pricing module
    # We only price candidates
    candidates = [e for e in evaluations if e["candidate"]]
    pricing_inputs = []
    for c in candidates:
        pricing_inputs.append({
            'resource_id': c['volume_id'],
            'region': c['region'],
            'size_gb': c['size_gib'],
            'iops': c['iops'],
            'throughput_mbps': c['throughput']
        })
        
    if ebs_gp2_to_gp3_pricing and pricing_inputs:
        enriched_pricing = ebs_gp2_to_gp3_pricing.calculate_savings(pricing_inputs, account_id=account_id)
        # Map them back by resource_id
        pricing_map = {p['resource_id']: p for p in enriched_pricing}
    else:
        pricing_map = {}

    for evaluation in evaluations:
        price_data = pricing_map.get(evaluation['volume_id'])
        finding = build_finding(
            evaluation,
            pricing_data=price_data
        )
        findings.append(finding)

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
        f"Account ID             : "
        f"{account_id}"
    )

    print(
        f"Region                 : "
        f"{REGION}"
    )

    print(
        f"EBS Volumes Scanned    : "
        f"{len(volumes)}"
    )

    print(
        f"GP2 Volumes             : "
        f"{gp2_count}"
    )

    print(
        f"GP2 -> GP3 Candidates   : "
        f"{candidate_count}"
    )

    print(
        f"GP2 Not In-use          : "
        f"{not_in_use_count}"
    )

    print(
        f"GP2 Unattached          : "
        f"{unattached_count}"
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