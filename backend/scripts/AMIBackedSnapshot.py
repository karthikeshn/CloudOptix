from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError


# ============================================================
# Configuration
# ============================================================

DEFAULT_REGION = "us-east-1"


# ============================================================
# Helper functions
# ============================================================

def calculate_age_days(start_time: datetime) -> float:
    """Return snapshot age in days."""
    now = datetime.now(timezone.utc)

    # AWS normally returns timezone-aware datetimes.
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)

    return round((now - start_time).total_seconds() / 86400, 2)


def build_snapshot_arn(
    account_id: str,
    region_name: str,
    snapshot_id: str,
) -> str:
    """Build the correct EBS snapshot ARN."""
    return (
        f"arn:aws:ec2:{region_name}:{account_id}:"
        f"snapshot/{snapshot_id}"
    )


def is_not_found_error(error: ClientError) -> bool:
    """Determine whether an AWS API error means a resource was not found."""
    error_code = error.response.get("Error", {}).get("Code", "")

    return error_code in {
        "InvalidSnapshot.NotFound",
        "InvalidSnapshotID.NotFound",
        "InvalidVolume.NotFound",
        "InvalidAMIID.NotFound",
        "ImageNotFound",
    }


# ============================================================
# AWS Resource Discovery
# ============================================================

def get_account_id(sts_client) -> str:
    """Get the current AWS account ID."""
    response = sts_client.get_caller_identity()
    return response["Account"]


def get_snapshot(
    ec2_client,
    snapshot_id: str,
) -> Dict[str, Any]:
    """Fetch one EBS snapshot."""
    response = ec2_client.describe_snapshots(
        SnapshotIds=[snapshot_id]
    )

    snapshots = response.get("Snapshots", [])

    if not snapshots:
        raise ValueError(
            f"Snapshot {snapshot_id} was not returned by AWS."
        )

    return snapshots[0]


# ============================================================
# Rule 1:
# Does the source EBS volume still exist?
# ============================================================

def check_source_volume(
    ec2_client,
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Check whether the snapshot's source EBS volume exists.

    Important:
    A missing source volume means the snapshot satisfies the
    'orphaned-snapshot-without-active-volume' condition.

    It does NOT automatically mean the snapshot is safe to delete.
    """

    volume_id = snapshot.get("VolumeId")

    if not volume_id:
        return {
            "source_volume_id": None,
            "source_volume_exists": False,
            "orphaned_by_volume_rule": True,
            "reason": "Snapshot has no source VolumeId.",
        }

    try:
        response = ec2_client.describe_volumes(
            VolumeIds=[volume_id]
        )

        volumes = response.get("Volumes", [])

        if volumes:
            return {
                "source_volume_id": volume_id,
                "source_volume_exists": True,
                "orphaned_by_volume_rule": False,
                "reason": (
                    f"Source volume {volume_id} currently exists."
                ),
            }

        return {
            "source_volume_id": volume_id,
            "source_volume_exists": False,
            "orphaned_by_volume_rule": True,
            "reason": (
                f"Source volume {volume_id} does not exist."
            ),
        }

    except ClientError as error:

        if is_not_found_error(error):
            return {
                "source_volume_id": volume_id,
                "source_volume_exists": False,
                "orphaned_by_volume_rule": True,
                "reason": (
                    f"Source volume {volume_id} no longer exists."
                ),
            }

        # Do NOT interpret permission/throttling/etc. as orphaned.
        raise


# ============================================================
# Rule 2:
# Is this snapshot currently referenced by an AMI?
# ============================================================

def find_amis_referencing_snapshot(
    ec2_client,
    snapshot_id: str,
) -> List[Dict[str, Any]]:
    """
    Find currently registered AMIs in this account that reference
    the target snapshot through their block-device mappings.

    There is no universal direct 'get AMIs for snapshot' API.
    Therefore we inspect the AMIs and build the reverse relationship.
    """

    matching_amis: List[Dict[str, Any]] = []

    paginator = ec2_client.get_paginator("describe_images")

    pages = paginator.paginate(
        Owners=["self"]
    )

    for page in pages:
        for image in page.get("Images", []):

            image_id = image.get("ImageId")

            if not image_id:
                continue

            block_device_mappings = image.get(
                "BlockDeviceMappings",
                [],
            )

            for mapping in block_device_mappings:

                ebs = mapping.get("Ebs", {})

                mapped_snapshot_id = ebs.get(
                    "SnapshotId"
                )

                if mapped_snapshot_id == snapshot_id:

                    matching_amis.append(
                        {
                            "ami_id": image_id,
                            "name": image.get("Name"),
                            "state": image.get("State"),
                            "creation_date": image.get(
                                "CreationDate"
                            ),
                            "root_device_name": image.get(
                                "RootDeviceName"
                            ),
                            "device_name": mapping.get(
                                "DeviceName"
                            ),
                        }
                    )

    return matching_amis


# ============================================================
# Rule 3:
# Does the associated AMI still exist?
#
# NOTE:
# This function is useful when you already know an AMI ID.
# Current AMI discovery is done above.
# ============================================================

def check_ami_exists(
    ec2_client,
    ami_id: str,
) -> Dict[str, Any]:
    """Check whether a specific AMI currently exists."""

    try:
        response = ec2_client.describe_images(
            ImageIds=[ami_id],
            Owners=["self"],
        )

        images = response.get("Images", [])

        if images:
            return {
                "ami_id": ami_id,
                "exists": True,
                "image": images[0],
            }

        return {
            "ami_id": ami_id,
            "exists": False,
            "image": None,
        }

    except ClientError as error:

        if is_not_found_error(error):
            return {
                "ami_id": ami_id,
                "exists": False,
                "image": None,
            }

        raise


# ============================================================
# FinOps classification
# ============================================================

def classify_snapshot(
    source_volume_result: Dict[str, Any],
    associated_amis: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Combine independent AWS facts into a FinOps classification.

    IMPORTANT:
    AMI-backed and orphaned are NOT mutually exclusive.

    Example:
        source volume missing
        +
        active AMI references snapshot

    means:

        orphaned_by_volume_rule = True
        currently_ami_backed = True

    We therefore keep these as separate properties.
    """

    source_volume_exists = source_volume_result[
        "source_volume_exists"
    ]

    currently_ami_backed = len(associated_amis) > 0

    if source_volume_exists:
        volume_status = "Active"
    else:
        volume_status = "Orphaned"

    if currently_ami_backed:
        ami_status = "AMI-backed"
    else:
        ami_status = "Not currently AMI-backed"

    return {
        "source_volume_exists": source_volume_exists,
        "volume_status": volume_status,
        "currently_ami_backed": currently_ami_backed,
        "ami_status": ami_status,
        "associated_amis": associated_amis,
    }


# ============================================================
# Recommendation
# ============================================================

def generate_recommendation(
    classification: Dict[str, Any],
    snapshot_id: str,
    size_gb: int,
    age_days: float,
) -> Dict[str, str]:
    """
    Generate a recommendation based on the classification.

    We intentionally DO NOT automatically recommend deletion when:
        - source volume is missing
        - but an active AMI still references the snapshot.

    That snapshot may still be required to launch instances
    from the AMI.
    """

    orphaned = classification["volume_status"] == "Orphaned"
    ami_backed = classification["currently_ami_backed"]

    associated_amis = classification["associated_amis"]

    # --------------------------------------------------------
    # Case 1:
    # Source volume exists + AMI exists
    # --------------------------------------------------------

    if not orphaned and ami_backed:

        ami_ids = ", ".join(
            ami["ami_id"]
            for ami in associated_amis
        )

        return {
            "type": "Active",
            "policy": "active-ami-backed-snapshot",
            "effort_level": "N/A",
            "recommendation": (
                f"Snapshot {snapshot_id} is associated with "
                f"active AMI(s): {ami_ids}. Keep the snapshot."
            ),
        }

    # --------------------------------------------------------
    # Case 2:
    # Source volume exists + no AMI
    # --------------------------------------------------------

    if not orphaned and not ami_backed:

        return {
            "type": "Active",
            "policy": "snapshot-with-active-source-volume",
            "effort_level": "Review",
            "recommendation": (
                f"Snapshot {snapshot_id} has an active source "
                f"volume. It is not currently referenced by an AMI. "
                f"Review its business purpose before deletion."
            ),
        }

    # --------------------------------------------------------
    # Case 3:
    # Source volume missing + AMI still exists
    # --------------------------------------------------------

    if orphaned and ami_backed:

        ami_ids = ", ".join(
            ami["ami_id"]
            for ami in associated_amis
        )

        return {
            "type": "Orphaned-source-volume",
            "policy": (
                "orphaned-source-volume-but-ami-still-active"
            ),
            "effort_level": "Review",
            "recommendation": (
                f"Snapshot {snapshot_id} has no active source "
                f"volume, but it is still referenced by active "
                f"AMI(s): {ami_ids}. Do NOT automatically delete "
                f"the snapshot. Review the AMI dependency first."
            ),
        }

    # --------------------------------------------------------
    # Case 4:
    # Source volume missing + no active AMI
    # --------------------------------------------------------

    return {
        "type": "Orphaned",
        "policy": "orphaned-snapshot-without-active-volume",
        "effort_level": "Low",
        "recommendation": (
            f"EBS snapshot {snapshot_id} "
            f"({size_gb} GB, {int(age_days)} days old) "
            f"has no active source volume and is not currently "
            f"referenced by an active AMI. "
            f"It is a potential cleanup candidate. "
            f"Review before deleting."
        ),
    }


# ============================================================
# Main FinOps analyzer
# ============================================================

def analyze_ami_backed_snapshot(
    snapshot_id: str,
    region_name: str = DEFAULT_REGION,
) -> Dict[str, Any]:

    ec2 = boto3.client(
        "ec2",
        region_name=region_name,
    )

    sts = boto3.client("sts")

    account_id = get_account_id(sts)

    # --------------------------------------------------------
    # 1. Snapshot metadata
    # --------------------------------------------------------

    snapshot = get_snapshot(
        ec2,
        snapshot_id,
    )

    size_gb = snapshot.get(
        "VolumeSize",
        0,
    )

    start_time = snapshot.get("StartTime")

    if not start_time:
        raise ValueError(
            f"Snapshot {snapshot_id} does not contain StartTime."
        )

    age_days = calculate_age_days(
        start_time
    )

    # --------------------------------------------------------
    # 2. Source volume relationship
    # --------------------------------------------------------

    source_volume_result = check_source_volume(
        ec2,
        snapshot,
    )

    # --------------------------------------------------------
    # 3. Current AMI relationship
    # --------------------------------------------------------

    associated_amis = find_amis_referencing_snapshot(
        ec2,
        snapshot_id,
    )

    # --------------------------------------------------------
    # 4. Classification
    # --------------------------------------------------------

    classification = classify_snapshot(
        source_volume_result,
        associated_amis,
    )

    # --------------------------------------------------------
    # 5. Recommendation
    # --------------------------------------------------------

    recommendation = generate_recommendation(
        classification,
        snapshot_id,
        size_gb,
        age_days,
    )

    # --------------------------------------------------------
    # 6. ARN
    # --------------------------------------------------------

    arn = build_snapshot_arn(
        account_id,
        region_name,
        snapshot_id,
    )

    # --------------------------------------------------------
    # 7. Human-readable message
    # --------------------------------------------------------

    associated_ami_ids = [
        ami["ami_id"]
        for ami in associated_amis
    ]

    if associated_ami_ids:
        ami_text = ", ".join(
            associated_ami_ids
        )
    else:
        ami_text = "None"

    message = (
        f"EBS snapshot {snapshot_id} "
        f"({size_gb} GB, {int(age_days)} days old). "
        f"Source volume: "
        f"{source_volume_result.get('source_volume_id') or 'None'}. "
        f"Source volume exists: "
        f"{source_volume_result['source_volume_exists']}. "
        f"Currently referenced by AMI(s): {ami_text}. "
        f"{recommendation['recommendation']}"
    )

    # --------------------------------------------------------
    # 8. Return normalized result
    # --------------------------------------------------------

    return {
        # AWS identity
        "accountId": account_id,
        "region": region_name,
        "resourceId": snapshot_id,
        "arn": arn,
        "service": "EBS Snapshot",

        # Resource metadata
        "sizeGB": size_gb,
        "startTime": start_time.isoformat(),
        "ageDays": age_days,
        "sourceVolumeId": source_volume_result.get(
            "source_volume_id"
        ),

        # Relationship facts
        "sourceVolumeExists": source_volume_result[
            "source_volume_exists"
        ],
        "currentlyAMIBacked": classification[
            "currently_ami_backed"
        ],
        "associatedAMIs": associated_amis,

        # FinOps classification
        "type": recommendation["type"],
        "policy": recommendation["policy"],
        "effortLevel": recommendation["effort_level"],
        "recommendation": recommendation[
            "recommendation"
        ],

        # Human-readable finding
        "message": message,

        # IMPORTANT:
        # Cost is intentionally NOT calculated here.
        #
        # These should come from your CUR + Athena
        # cost engine:
        #
        # "currentDailyCost": ...,
        # "currentMonthToDateCost": ...,
        # "previousMonthCost": ...,

        # Workflow fields
        "category": "AMI Backed Snapshot",
    }


# ============================================================
# Test
# ============================================================


# ============================================================
# EXPORT TO EXCEL
# ============================================================

def export_to_excel(
    findings,
    filename: str,
):
    from typing import List, Dict, Any
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
    
    if isinstance(findings, dict):
        findings = [findings]

    for finding in findings:
        flat_finding = {}
        extra_attributes = []
        
        for key, value in finding.items():
            if isinstance(value, (dict, list)):
                import json
                str_val = json.dumps(value, default=str)
            else:
                str_val = value

            if key in STANDARD_COLUMNS:
                flat_finding[key] = str_val
            else:
                extra_attributes.append(f"{key}: {str_val}")
                
        standard_row = {col: "" for col in STANDARD_COLUMNS}
        
        for k, v in flat_finding.items():
            standard_row[k] = v
            
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
    df.to_excel(filename, index=False)
    print(f"\\nExcel report created:\\n{filename}")

if __name__ == "__main__":
    import boto3
    import json
    import os
    
    target_region = os.environ.get("AWS_REGION")
    
    if target_region:
        regions = [target_region]
        print(f"Discovered 1 target region from environment: {target_region}")
    else:
        # Use a default region just to fetch the list of all regions
        base_ec2 = boto3.client("ec2", region_name=DEFAULT_REGION)
        
        print("Fetching all enabled AWS regions...")
        try:
            regions_response = base_ec2.describe_regions()
            regions = [r["RegionName"] for r in regions_response.get("Regions", [])]
        except Exception as e:
            print(f"Failed to fetch regions: {e}")
            exit(1)
            
        print(f"Discovered {len(regions)} regions to scan.")
    
    all_findings = []
    
    for region in regions:
        print(f"\n========================================")
        print(f"Scanning region: {region}")
        print(f"========================================")
        
        regional_ec2 = boto3.client("ec2", region_name=region)
        paginator = regional_ec2.get_paginator("describe_snapshots")
        
        snapshot_count = 0
        try:
            for page in paginator.paginate(OwnerIds=['self']):
                snapshots = page.get("Snapshots", [])
                for snap in snapshots:
                    snapshot_count += 1
                    target_snapshot_id = snap["SnapshotId"]
                    print(f"Evaluating snapshot: {target_snapshot_id}")
                    
                    try:
                        result = analyze_ami_backed_snapshot(
                            snapshot_id=target_snapshot_id,
                            region_name=region,
                        )
                        all_findings.append(result)
                    except Exception as e:
                        print(f"Error evaluating snapshot {target_snapshot_id}: {e}")
        except Exception as e:
            print(f"Failed to fetch snapshots in {region}: {e}")
            
        print(f"Total snapshots evaluated in {region}: {snapshot_count}")
        
    print(f"\n========================================")
    print(f"Scan complete. Total snapshots found across all regions: {len(all_findings)}")
    print(f"========================================")

    if all_findings:
        export_to_excel(
            findings=all_findings,
            filename="snapshot_report.xlsx",
        )
    else:
        print("No snapshots found in any region. No report generated.")
