from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
import logging
import pandas as pd
import json

import boto3
from botocore.config import Config

# ============================================================
# AWS CLIENT CONFIGURATION
# ============================================================
AWS_CONFIG = Config(
    retries={
        "mode": "adaptive",
        "max_attempts": 10,
    }
)

def create_clients(region_name: str):
    ec2 = boto3.client("ec2", region_name=region_name, config=AWS_CONFIG)
    sts = boto3.client("sts", config=AWS_CONFIG)
    return ec2, sts

def get_account_id(sts) -> str:
    return sts.get_caller_identity()["Account"]

# ============================================================
# FETCH & EVALUATE
# ============================================================
def fetch_all_ebs_volumes(ec2) -> List[Dict[str, Any]]:
    volumes = []
    paginator = ec2.get_paginator("describe_volumes")
    for page in paginator.paginate():
        volumes.extend(page.get("Volumes", []))
    return volumes

def is_unattached_volume(volume: Dict[str, Any]) -> bool:
    state = volume.get("State")
    attachments = volume.get("Attachments", [])
    return state == "available" and len(attachments) == 0

def calculate_age_days(create_time: datetime):
    if create_time.tzinfo is None:
        create_time = create_time.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return round((now - create_time).total_seconds() / 86400, 2)

# ============================================================
# BUILD FINOPS FINDING
# ============================================================
def build_volume_finding(volume: Dict[str, Any], account_id: str, region_name: str) -> Dict[str, Any]:
    volume_id = volume["VolumeId"]
    size_gib = volume.get("Size", 0)
    volume_type = volume.get("VolumeType", "unknown")
    availability_zone = volume.get("AvailabilityZone")
    state = volume.get("State")
    create_time = volume.get("CreateTime")

    age_days = calculate_age_days(create_time) if create_time else None
    is_unattached = is_unattached_volume(volume)
    
    if is_unattached:
        status_text = "Idle"
        recommendation = "EBS volume is unattached. Review and delete if it is no longer required."
        effort_level = "Low"
    else:
        status_text = "Active"
        recommendation = "EBS volume is attached. Keep."
        effort_level = "None"

    arn = f"arn:aws:ec2:{region_name}:{account_id}:volume/{volume_id}"
    policy = "orphaned-ebs-volume-unattached"

    description = (
        f"Volume {volume_id} in {availability_zone} "
        f"({size_gib} GiB, {volume_type}) is "
        f"{'unattached' if is_unattached else 'attached'}. "
        f"Volume state: {state}. "
        f"Age in days: {int(age_days) if age_days is not None else 'Unknown'}."
    )

    return {
        "accountId": account_id,
        "region": region_name,
        "resourceNameOrId": volume_id,
        "resourceArn": arn,
        "service": "EBS",
        "type": "Unattached" if is_unattached else "Attached",
        "policy": policy,
        "effortLevel": effort_level,
        "status": status_text,
        "recommendation": recommendation,
        "description": description,
        # Metrics for potential cost savings calculations
        "volumeId": volume_id,
        "availabilityZone": availability_zone,
        "volumeType": volume_type,
        "sizeGiB": size_gib,
        "state": state,
        "createTime": create_time.isoformat() if create_time else None,
        "ageDays": age_days,
        "encrypted": volume.get("Encrypted", False),
        "currentDailyCost": "To be updated",
        "currentMonthlyCost": "To be updated"
    }

def scan_ebs_volumes_in_region(region_name: str, account_id: str):
    ec2, _ = create_clients(region_name)
    volumes = fetch_all_ebs_volumes(ec2)
    findings = [build_volume_finding(v, account_id, region_name) for v in volumes]
    return volumes, findings

# ============================================================
# EXPORT TO EXCEL
# ============================================================
def export_to_excel(findings, filename: str):
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
    for finding in (findings if isinstance(findings, list) else [findings]):
        flat_finding = {}
        extra_attributes = []
        
        for key, value in finding.items():
            str_val = json.dumps(value, default=str) if isinstance(value, (dict, list)) else value
            if key in STANDARD_COLUMNS:
                flat_finding[key] = str_val
            else:
                extra_attributes.append(f"{key}: {str_val}")
                
        standard_row = {col: "" for col in STANDARD_COLUMNS}
        standard_row.update(flat_finding)
            
        existing_desc = standard_row.get("description", "") or ""
        if extra_attributes:
            extra_str = " | ".join(extra_attributes)
            standard_row["description"] = f"{existing_desc} | {extra_str}" if existing_desc else extra_str
                
        flat_findings.append(standard_row)

    df = pd.DataFrame(flat_findings, columns=STANDARD_COLUMNS)
    df.to_excel(filename, index=False)
    logging.getLogger(__name__).info(f"Excel report created: {filename}")


# ============================================================
# MAIN ORCHESTRATOR
# ============================================================
def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)
    logger.info("Starting FinOps Policy: EBS Unattached")
    
    # Initialize with default region to grab account ID and active regions
    base_ec2, base_sts = create_clients("us-east-1")
    account_id = get_account_id(base_sts)
    
    try:
        regions_response = base_ec2.describe_regions()
        regions = [r["RegionName"] for r in regions_response.get("Regions", [])]
    except Exception as e:
        logger.error(f"Failed to fetch regions: {e}")
        return
        
    logger.info(f"Discovered {len(regions)} regions to scan.")
    
    all_volumes = []
    all_findings = []
    
    for region in regions:
        logger.info(f"Scanning region: {region}...")
        try:
            volumes, findings = scan_ebs_volumes_in_region(region, account_id)
            all_volumes.extend(volumes)
            all_findings.extend(findings)
            logger.info(f"Evaluated {len(volumes)} volumes in {region}")
        except Exception as e:
            logger.error(f"Failed to scan region {region}: {e}")
            
    # Filter to only export Unattached volumes to the final report
    unattached_findings = [f for f in all_findings if f.get("type") == "Unattached"]
    
    if unattached_findings:
        export_to_excel(unattached_findings, "ebs_unattached_report.xlsx")
    else:
        logger.info("No unattached volumes found! You are optimized.")
    
    logger.info(f"\nSCAN COMPLETED")
    logger.info(f"Total Regions Scanned: {len(regions)}")
    logger.info(f"Total Volumes Evaluated: {len(all_volumes)}")
    logger.info(f"Unattached Volumes Exported: {len(unattached_findings)}")

if __name__ == "__main__":
    main()
