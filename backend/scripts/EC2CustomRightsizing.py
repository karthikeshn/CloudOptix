from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

# ============================================================
# AWS CLIENT CONFIGURATION
# ============================================================
AWS_CONFIG = Config(retries={"mode": "adaptive", "max_attempts": 10})

# Rightsizing size step-down dictionary
SIZE_STEPPER = {
    "metal": "24xlarge",
    "24xlarge": "16xlarge",
    "16xlarge": "12xlarge",
    "12xlarge": "8xlarge",
    "8xlarge": "4xlarge",
    "4xlarge": "2xlarge",
    "2xlarge": "xlarge",
    "xlarge": "large",
    "large": "medium",
    "medium": "small",
    "small": "micro",
    "micro": "nano"
}

def create_clients(region_name: str):
    ec2 = boto3.client("ec2", region_name=region_name, config=AWS_CONFIG)
    cw = boto3.client("cloudwatch", region_name=region_name, config=AWS_CONFIG)
    sts = boto3.client("sts", region_name=region_name, config=AWS_CONFIG)
    return ec2, cw, sts

def get_account_id(sts) -> str:
    return sts.get_caller_identity()["Account"]

def get_metric_peak(cw, instance_id: str, metric_name: str, unit: str = "Percent") -> float:
    try:
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=30)

        response = cw.get_metric_statistics(
            Namespace="AWS/EC2",
            MetricName=metric_name,
            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400, # Daily peaks
            Statistics=["Maximum"],
            Unit=unit
        )
        datapoints = response.get("Datapoints", [])
        if not datapoints:
            return 0.0
        
        return max(dp["Maximum"] for dp in datapoints)
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to fetch metric {metric_name} for {instance_id}: {e}")
        return 0.0

def process_instance(cw, instance: Dict[str, Any], account_id: str, region: str) -> Optional[Dict[str, Any]]:
    instance_id = instance["InstanceId"]
    instance_type = instance["InstanceType"]
    
    # Check if instance type can be split
    if "." not in instance_type:
        return None
        
    family, size = instance_type.split(".", 1)
    
    # Is it the smallest size already?
    if size not in SIZE_STEPPER:
        return None
        
    target_size = SIZE_STEPPER[size]
    target_instance_type = f"{family}.{target_size}"

    # Fetch Metrics
    peak_cpu = get_metric_peak(cw, instance_id, "CPUUtilization", "Percent")
    peak_net_in_bytes = get_metric_peak(cw, instance_id, "NetworkIn", "Bytes")
    peak_net_out_bytes = get_metric_peak(cw, instance_id, "NetworkOut", "Bytes")
    
    # Convert Network Bytes (which is accumulated over the 5 minute period in CW) to Mbps
    # CW NetworkIn is bytes over 5 minutes. peak_net_in_bytes / 300 seconds = bytes/sec
    # bytes/sec * 8 / 1,000,000 = Mbps
    peak_net_in_mbps = (peak_net_in_bytes / 300) * 8 / 1000000
    peak_net_out_mbps = (peak_net_out_bytes / 300) * 8 / 1000000
    
    # Safety Gates
    if peak_cpu >= 20.0 or peak_net_in_mbps >= 500.0 or peak_net_out_mbps >= 500.0:
        return None
        
    status_text = "Actionable"
    recommendation = f"Downsize EC2 instance {instance_id} from {instance_type} to {target_instance_type}."
    effort_level = "Medium"
    policy = "ec2-custom-cloudwatch-rightsizing"
    
    description = (
        f"Instance {instance_id} ({instance_type}) is safely over-provisioned based on 30-day metrics. "
        f"Peak CPU: {peak_cpu:.1f}%. "
        f"Peak Network In: {peak_net_in_mbps:.1f} Mbps. Peak Network Out: {peak_net_out_mbps:.1f} Mbps. "
        f"Recommending downsize to {target_instance_type} to preserve processor architecture."
    )

    arn = f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}"

    return {
        "title": "EC2 Custom Rightsizing (Metrics)",
        "category": "Compute",
        "accountId": account_id,
        "region": region,
        "resourceId": instance_id,
        "resourceArn": arn,
        "service": "EC2",
        "type": "Rightsizing",
        "policy": policy,
        "effortLevel": effort_level,
        "status": status_text,
        "recommendation": recommendation,
        "description": description,
        "currentInstanceType": instance_type,
        "targetInstanceType": target_instance_type,
        "currentDailyCost": "To be updated",
        "currentMonthlyCost": "To be updated",
        "estimatedMonthlySavings": "To be updated"
    }

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Starting FinOps Policy: EC2 Custom Rightsizing")
    
    # Get all regions
    base_ec2, _, base_sts = create_clients("us-east-1")
    account_id = get_account_id(base_sts)
    
    try:
        regions_response = base_ec2.describe_regions()
        regions = [r["RegionName"] for r in regions_response.get("Regions", [])]
    except Exception as e:
        logger.error(f"Failed to fetch regions: {e}")
        return
        
    all_findings = []
    
    for region in regions:
        logger.info(f"Scanning region {region}...")
        try:
            ec2, cw, _ = create_clients(region)
            response = ec2.describe_instances(Filters=[{"Name": "instance-state-name", "Values": ["running"]}])
            instances = [i for r in response.get("Reservations", []) for i in r.get("Instances", [])]
            
            if not instances:
                continue
                
            logger.info(f"Analyzing CloudWatch metrics for {len(instances)} instances in {region}...")
            
            for inst in instances:
                finding = process_instance(cw, inst, account_id, region)
                if finding:
                    all_findings.append(finding)
        except Exception as e:
            logger.error(f"Failed to process region {region}: {e}")
            
    logger.info(f"Found {len(all_findings)} safe rightsizing opportunities across all regions.")

    # Pricing Logic
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        import importlib
        ec2_custom_rightsizing_pricing = importlib.import_module("pricing_rules.ec2_custom_rightsizing_pricing")
        
        pricing_inputs = []
        for finding in all_findings:
            pricing_inputs.append({
                "resource_id": finding["resourceId"],
                "currentInstanceType": finding["currentInstanceType"],
                "targetInstanceType": finding["targetInstanceType"]
            })
                
        if pricing_inputs:
            logger.info("Executing pricing calculations...")
            enriched_pricing = ec2_custom_rightsizing_pricing.calculate_savings(pricing_inputs, account_id=account_id)
            pricing_map = {p['resource_id']: p for p in enriched_pricing}
            
            for finding in all_findings:
                if finding["resourceId"] in pricing_map:
                    p_data = pricing_map[finding["resourceId"]]
                    finding["currentDailyCost"] = p_data.get("currentDailyCost", "To be updated")
                    finding["currentMonthlyCost"] = p_data.get("currentMonthlyCost", "To be updated")
                    finding["estimatedMonthlySavings"] = p_data.get("estimatedMonthlySavings", "To be updated")
    except ImportError as e:
        logger.warning(f"Pricing module not found. Skipping pricing calculation. {e}")
    except Exception as e:
        logger.error(f"Failed to execute pricing logic: {e}")
            
    export_to_excel(all_findings, "ec2_custom_rightsizing_report.xlsx")
    
    logger.info(f"\n==================================================")
    logger.info("SCAN COMPLETED")
    logger.info(f"Total Rightsizing Opportunities Found: {len(all_findings)}")
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
    if not flat_findings:
        logger.warning(f"No findings to export. Empty report generated: {filename}")
        df = pd.DataFrame(columns=STANDARD_COLUMNS)
    else:
        df = pd.DataFrame(flat_findings, columns=STANDARD_COLUMNS)
    df.to_excel(filename, index=False)
    logger.info(f"Excel report created: {filename}")

if __name__ == "__main__":
    main()
