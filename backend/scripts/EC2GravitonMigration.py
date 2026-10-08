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

def fetch_running_x86_instances(ec2) -> List[Dict[str, Any]]:
    instances = []
    paginator = ec2.get_paginator("describe_instances")
    
    # We only care about running instances for now
    for page in paginator.paginate(Filters=[{"Name": "instance-state-name", "Values": ["running"]}]):
        for reservation in page.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                # Filter for x86_64 architecture and ensure it is NOT a Windows instance (Graviton is Linux-only)
                is_windows = instance.get("Platform") == "windows" or "Windows" in instance.get("PlatformDetails", "")
                
                if instance.get("Architecture") == "x86_64" and not is_windows:
                    instances.append(instance)
                    
    return instances

def build_instance_finding(
    instance: Dict[str, Any],
    account_id: str,
    region_name: str,
) -> Dict[str, Any]:
    instance_id = instance["InstanceId"]
    instance_type = instance.get("InstanceType", "unknown")
    state = instance.get("State", {}).get("Name", "unknown")
    launch_time = instance.get("LaunchTime")

    status_text = "Actionable"
    recommendation = f"Migrate EC2 instance {instance_id} ({instance_type}) to AWS Graviton (e.g., t4g, m6g) for up to 20% cost savings."
    effort_level = "Medium"

    arn = f"arn:aws:ec2:{region_name}:{account_id}:instance/{instance_id}"
    policy = "ec2-graviton-migration"

    description = (
        f"Instance {instance_id} is running on x86_64 architecture with instance type {instance_type}. "
        f"Migrating to a Graviton-based instance can reduce costs and improve price performance."
    )

    return {
        "title": "EC2 x86 to Graviton Migration",
        "category": "Compute",
        "accountId": account_id,
        "region": region_name,
        "resourceId": instance_id,
        "resourceArn": arn,
        "service": "EC2",
        "type": "Modernization",
        "policy": policy,
        "effortLevel": effort_level,
        "status": status_text,
        "recommendation": recommendation,
        "description": description,
        "instanceId": instance_id,
        "instanceType": instance_type,
        "architecture": instance.get("Architecture"),
        "launchTime": launch_time.isoformat() if launch_time else None,
        "currentDailyCost": "To be updated",
        "currentMonthlyCost": "To be updated",
        "estimatedMonthlySavings": "To be updated"
    }

def scan_region(region_name: str, account_id: str):
    ec2, _ = create_clients(region_name)
    instances = fetch_running_x86_instances(ec2)
    
    findings = []
    for inst in instances:
        findings.append(build_instance_finding(inst, account_id, region_name))

    return instances, findings

def main():
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Starting FinOps Policy: EC2 Graviton Migration")
    
    base_ec2, base_sts = create_clients("us-east-1")
    account_id = get_account_id(base_sts)
    
    try:
        regions_response = base_ec2.describe_regions()
        regions = [r["RegionName"] for r in regions_response.get("Regions", [])]
    except Exception as e:
        logger.error(f"Failed to fetch regions: {e}")
        import sys
        sys.exit(1)
        
    all_instances = []
    all_findings = []
    
    for region in regions:
        logger.info(f"\n========================================")
        logger.info(f"Scanning region: {region}")
        logger.info(f"========================================")
        
        try:
            instances, findings = scan_region(region, account_id)
            all_instances.extend(instances)
            all_findings.extend(findings)
            logger.info(f"Evaluated and found {len(instances)} x86 instances in {region}")
        except Exception as e:
            logger.error(f"Failed to scan region {region}: {e}")

    # Pricing Logic
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from pricing_rules import ec2_graviton_migration_pricing
        
        pricing_inputs = []
        for finding in all_findings:
            pricing_inputs.append({
                "resource_id": finding["instanceId"],
                "region": finding["region"],
                "instance_type": finding["instanceType"]
            })
                
        if pricing_inputs:
            enriched_pricing = ec2_graviton_migration_pricing.calculate_savings(pricing_inputs, account_id=account_id)
            pricing_map = {p['resource_id']: p for p in enriched_pricing}
            
            for finding in all_findings:
                if finding["instanceId"] in pricing_map:
                    p_data = pricing_map[finding["instanceId"]]
                    finding["currentDailyCost"] = p_data.get("currentDailyCost", "To be updated")
                    finding["currentMonthlyCost"] = p_data.get("currentMonthlyCost", "To be updated")
                    finding["estimatedMonthlySavings"] = p_data.get("estimatedMonthlySavings", "To be updated")
    except ImportError:
        logger.warning("Pricing module not found. Skipping pricing calculation.")
    except Exception as e:
        logger.error(f"Failed to execute pricing logic: {e}")
            
    export_to_excel(all_findings, "ec2_graviton_migration_report.xlsx")
    
    logger.info(f"\n==================================================")
    logger.info("SCAN COMPLETED")
    logger.info(f"Total Regions Scanned: {len(regions)}")
    logger.info(f"Total Migration Opportunities Found: {len(all_findings)}")
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
