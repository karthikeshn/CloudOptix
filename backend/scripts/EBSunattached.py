
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


# ============================================================
# CREATE AWS CLIENTS
# ============================================================

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


# ============================================================
# ACCOUNT ID
# ============================================================

def get_account_id(sts) -> str:

    return sts.get_caller_identity()["Account"]


# ============================================================
# FETCH ALL EBS VOLUMES IN A REGION
# ============================================================

def fetch_all_ebs_volumes(
    ec2,
) -> List[Dict[str, Any]]:
    """
    Automatically fetch ALL EBS volumes in the region.

    Pagination is handled using the boto3 paginator.
    """

    volumes = []

    paginator = ec2.get_paginator(
        "describe_volumes"
    )

    for page in paginator.paginate():

        page_volumes = page.get(
            "Volumes",
            []
        )

        volumes.extend(page_volumes)

    return volumes


# ============================================================
# CHECK WHETHER VOLUME IS UNATTACHED
# ============================================================

def is_unattached_volume(
    volume: Dict[str, Any]
) -> bool:

    state = volume.get(
        "State"
    )

    attachments = volume.get(
        "Attachments",
        []
    )

    return (
        state == "available"
        and len(attachments) == 0
    )


# ============================================================
# CALCULATE AGE
# ============================================================

def calculate_age_days(
    create_time: datetime
):

    if create_time.tzinfo is None:
        create_time = create_time.replace(
            tzinfo=timezone.utc
        )

    now = datetime.now(timezone.utc)

    return round(
        (
            now - create_time
        ).total_seconds()
        / 86400,
        2,
    )


# ============================================================
# BUILD FINOPS FINDING
# ============================================================

def build_volume_finding(
    volume: Dict[str, Any],
    account_id: str,
    region_name: str,
) -> Dict[str, Any]:

    volume_id = volume["VolumeId"]
    size_gib = volume.get("Size", 0)
    volume_type = volume.get("VolumeType", "unknown")
    availability_zone = volume.get("AvailabilityZone")
    state = volume.get("State")
    create_time = volume.get("CreateTime")

    age_days = None
    if create_time:
        age_days = calculate_age_days(create_time)

    encrypted = volume.get("Encrypted", False)
    
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
        "title": "EBS Volume Unattached",
        "category": "Storage & Volumes",
        "accountId": account_id,
        "region": region_name,
        "resourceId": volume_id,
        "resourceArn": arn,
        "service": "EBS",
        "type": "Unattached" if is_unattached else "Attached",
        "policy": policy,
        "effortLevel": effort_level,
        "status": status_text,
        "recommendation": recommendation,
        "description": description,
        "volumeId": volume_id,
        "availabilityZone": availability_zone,
        "volumeType": volume_type,
        "sizeGiB": size_gib,
        "createTime": create_time.isoformat() if create_time else None,
        "ageDays": age_days,
        "encrypted": encrypted,
        "currentDailyCost": "To be updated",
        "currentMonthlyCost": "To be updated"
    }


# ============================================================
# SCAN ALL EBS VOLUMES IN REGION
# ============================================================

def scan_ebs_volumes_in_region(
    region_name: str,
    account_id: str,
):
    ec2, _ = create_clients(region_name)

    volumes = fetch_all_ebs_volumes(ec2)
    findings = []

    for volume in volumes:
        if is_unattached_volume(volume):
            finding = build_volume_finding(
                volume=volume,
                account_id=account_id,
                region_name=region_name,
            )
            findings.append(finding)

    return volumes, findings


# ============================================================
# MAIN
# ============================================================


def main():
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Starting FinOps Policy: EBS Unattached")
    
    # Need to fetch regions, use a default region to initialize
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
    
    all_volumes = []
    all_findings = []
    
    for region in regions:
        logger.info(f"\n========================================")
        logger.info(f"Scanning region: {region}")
        logger.info(f"========================================")
        
        try:
            volumes, findings = scan_ebs_volumes_in_region(region, account_id)
            all_volumes.extend(volumes)
            all_findings.extend(findings)
            logger.info(f"Evaluated {len(volumes)} volumes in {region}")
        except Exception as e:
            logger.error(f"Failed to scan region {region}: {e}")
    # --------------------------------------------------------
    # Execute Pricing Logic
    # --------------------------------------------------------
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from pricing_rules import ebs_unattached_pricing
        
        # Build pricing input from findings
        pricing_inputs = []
        for finding in all_findings:
            if finding["status"] == "Idle":
                pricing_inputs.append({
                    "resource_id": finding["volumeId"],
                    "region": finding["region"],
                    "size_gb": finding["sizeGiB"],
                    "volume_type": finding["volumeType"]
                })
                
        if pricing_inputs:
            enriched_pricing = ebs_unattached_pricing.calculate_savings(pricing_inputs, account_id=account_id)
            pricing_map = {p['resource_id']: p for p in enriched_pricing}
            
            for finding in all_findings:
                if finding["volumeId"] in pricing_map:
                    p_data = pricing_map[finding["volumeId"]]
                    finding["currentDailyCost"] = p_data.get("currentDailyCost", "To be updated")
                    finding["currentMonthlyCost"] = p_data.get("currentMonthlyCost", "To be updated")
                    finding["estimatedMonthlySavings"] = p_data.get("estimatedMonthlySavings", "To be updated")
    except ImportError:
        logger.warning("ebs_unattached_pricing module not found. Skipping pricing calculation.")
    except Exception as e:
        logger.error(f"Failed to execute pricing logic: {e}")
            
    export_to_excel(all_findings, "ebs_unattached_report.xlsx")
    
    logger.info(f"\n==================================================")
    logger.info("SCAN COMPLETED")
    logger.info(f"Total Regions Scanned: {len(regions)}")
    logger.info(f"Total Volumes Evaluated: {len(all_volumes)}")
    logger.info(f"Total Findings Exported: {len(all_findings)}")
    logger.info(f"==================================================")


# ============================================================
# EXPORT TO EXCEL
# ============================================================

def export_to_excel(
    findings,
    filename: str,
):
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

