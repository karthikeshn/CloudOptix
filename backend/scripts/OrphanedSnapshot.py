from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

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
    ec2 = boto3.client(
        "ec2",
        region_name=region_name,
        config=AWS_CONFIG,
    )
    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG,
    )
    return ec2, sts

def get_account_id(sts) -> str:
    return sts.get_caller_identity()["Account"]

def fetch_all_active_volume_ids(ec2) -> List[str]:
    volume_ids = []
    paginator = ec2.get_paginator("describe_volumes")
    for page in paginator.paginate():
        for vol in page.get("Volumes", []):
            volume_ids.append(vol["VolumeId"])
    return volume_ids

def fetch_all_ami_snapshot_ids(ec2, account_id: str) -> List[str]:
    snapshot_ids = set()
    paginator = ec2.get_paginator("describe_images")
    for page in paginator.paginate(Owners=["self"]):
        for image in page.get("Images", []):
            for bdm in image.get("BlockDeviceMappings", []):
                ebs = bdm.get("Ebs", {})
                if "SnapshotId" in ebs:
                    snapshot_ids.add(ebs["SnapshotId"])
    return list(snapshot_ids)

def fetch_all_owned_snapshots(ec2, account_id: str) -> List[Dict[str, Any]]:
    snapshots = []
    paginator = ec2.get_paginator("describe_snapshots")
    for page in paginator.paginate(OwnerIds=["self"]):
        snapshots.extend(page.get("Snapshots", []))
    return snapshots

def calculate_age_days(create_time: datetime):
    if create_time.tzinfo is None:
        create_time = create_time.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return round((now - create_time).total_seconds() / 86400, 2)

def build_snapshot_finding(
    snapshot: Dict[str, Any],
    account_id: str,
    region_name: str,
) -> Dict[str, Any]:
    snapshot_id = snapshot["SnapshotId"]
    volume_id = snapshot.get("VolumeId", "unknown")
    size_gib = snapshot.get("VolumeSize", 0)
    state = snapshot.get("State")
    create_time = snapshot.get("StartTime")
    
    age_days = None
    if create_time:
        age_days = calculate_age_days(create_time)

    status_text = "Idle"
    recommendation = "EBS snapshot is orphaned (original volume deleted and no active AMI). Delete to save costs."
    effort_level = "Low"

    arn = f"arn:aws:ec2:{region_name}:{account_id}:snapshot/{snapshot_id}"
    policy = "orphaned-ebs-snapshot"

    description = (
        f"Snapshot {snapshot_id} (VolumeId: {volume_id}, Size: {size_gib} GiB) "
        f"is orphaned. State: {state}. Age: {int(age_days) if age_days is not None else 'Unknown'} days."
    )

    return {
        "title": "Orphaned EBS Snapshot",
        "category": "Storage & Volumes",
        "accountId": account_id,
        "region": region_name,
        "resourceId": snapshot_id,
        "resourceArn": arn,
        "service": "EBS Snapshot",
        "type": "Orphaned",
        "policy": policy,
        "effortLevel": effort_level,
        "status": status_text,
        "recommendation": recommendation,
        "description": description,
        "snapshotId": snapshot_id,
        "volumeId": volume_id,
        "sizeGiB": size_gib,
        "createTime": create_time.isoformat() if create_time else None,
        "ageDays": age_days,
        "currentDailyCost": "To be updated",
        "currentMonthlyCost": "To be updated",
        "estimatedMonthlySavings": "To be updated"
    }

def scan_orphaned_snapshots_in_region(region_name: str, account_id: str):
    ec2, _ = create_clients(region_name)

    active_volumes = set(fetch_all_active_volume_ids(ec2))
    ami_snapshots = set(fetch_all_ami_snapshot_ids(ec2, account_id))
    all_snapshots = fetch_all_owned_snapshots(ec2, account_id)
    
    findings = []
    orphaned_snapshots = []

    for snap in all_snapshots:
        if snap.get("State") != "completed":
            continue
            
        vol_id = snap.get("VolumeId")
        snap_id = snap.get("SnapshotId")
        
        if (not vol_id or vol_id not in active_volumes) and (snap_id not in ami_snapshots):
            orphaned_snapshots.append(snap)
            findings.append(build_snapshot_finding(snap, account_id, region_name))

    return orphaned_snapshots, findings

def main():
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Starting FinOps Policy: Orphaned EBS Snapshots")
    
    base_ec2, base_sts = create_clients("us-east-1")
    account_id = get_account_id(base_sts)
    
    try:
        regions_response = base_ec2.describe_regions()
        regions = [r["RegionName"] for r in regions_response.get("Regions", [])]
    except Exception as e:
        logger.error(f"Failed to fetch regions: {e}")
        import sys
        sys.exit(1)
        
    logger.info(f"Discovered {len(regions)} regions to scan.")
    
    all_orphaned_snapshots = []
    all_findings = []
    
    for region in regions:
        logger.info(f"\n========================================")
        logger.info(f"Scanning region: {region}")
        logger.info(f"========================================")
        
        try:
            snapshots, findings = scan_orphaned_snapshots_in_region(region, account_id)
            all_orphaned_snapshots.extend(snapshots)
            all_findings.extend(findings)
            logger.info(f"Evaluated and found {len(snapshots)} orphaned snapshots in {region}")
        except Exception as e:
            logger.error(f"Failed to scan region {region}: {e}")

    # Pricing Logic
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from pricing_rules import orphaned_snapshot_pricing
        
        pricing_inputs = []
        for finding in all_findings:
            pricing_inputs.append({
                "resource_id": finding["snapshotId"],
                "region": finding["region"],
                "size_gb": finding["sizeGiB"]
            })
                
        if pricing_inputs:
            enriched_pricing = orphaned_snapshot_pricing.calculate_savings(pricing_inputs, account_id=account_id)
            pricing_map = {p['resource_id']: p for p in enriched_pricing}
            
            for finding in all_findings:
                if finding["snapshotId"] in pricing_map:
                    p_data = pricing_map[finding["snapshotId"]]
                    finding["currentDailyCost"] = p_data.get("currentDailyCost", "To be updated")
                    finding["currentMonthlyCost"] = p_data.get("currentMonthlyCost", "To be updated")
                    finding["estimatedMonthlySavings"] = p_data.get("estimatedMonthlySavings", "To be updated")
    except ImportError:
        logger.warning("orphaned_snapshot_pricing module not found. Skipping pricing calculation.")
    except Exception as e:
        logger.error(f"Failed to execute pricing logic: {e}")
            
    export_to_excel(all_findings, "orphaned_snapshot_report.xlsx")
    
    logger.info(f"\n==================================================")
    logger.info("SCAN COMPLETED")
    logger.info(f"Total Regions Scanned: {len(regions)}")
    logger.info(f"Total Orphaned Snapshots Found: {len(all_findings)}")
    logger.info(f"==================================================")

def export_to_excel(findings, filename: str):
    from typing import List, Dict, Any
    STANDARD_COLUMNS = [
        "id", "title", "category", "owner",
        "assignedTo", "status",
        "accountId", "region", "resourceId",
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
    import logging
    logger = logging.getLogger(__name__)
    df = pd.DataFrame(flat_findings, columns=STANDARD_COLUMNS)
    df.to_excel(filename, index=False)
    logger.info(f"Excel report created: {filename}")

if __name__ == "__main__":
    main()
