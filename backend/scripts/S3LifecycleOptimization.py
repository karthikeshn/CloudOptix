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

def create_clients():
    s3 = boto3.client("s3", config=AWS_CONFIG)
    sts = boto3.client("sts", config=AWS_CONFIG)
    return s3, sts

def get_account_id(sts) -> str:
    return sts.get_caller_identity()["Account"]

def check_bucket_lifecycle(s3, bucket_name: str) -> bool:
    try:
        s3.get_bucket_lifecycle_configuration(Bucket=bucket_name)
        return True # Has lifecycle policy
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchLifecycleConfiguration':
            return False
        # Ignore other errors like AccessDenied and assume False or skip. We'll return True to skip if we can't access it.
        return True

def fetch_buckets_without_lifecycle(s3) -> List[str]:
    unoptimized_buckets = []
    response = s3.list_buckets()
    buckets = response.get("Buckets", [])
    
    for bucket in buckets:
        bucket_name = bucket["Name"]
        if not check_bucket_lifecycle(s3, bucket_name):
            unoptimized_buckets.append(bucket_name)
            
    return unoptimized_buckets

def build_bucket_finding(
    bucket_name: str,
    account_id: str,
) -> Dict[str, Any]:

    status_text = "Actionable"
    recommendation = f"Attach an S3 Lifecycle Policy to bucket {bucket_name} to transition older objects to Infrequent Access or Glacier, or enable S3 Intelligent-Tiering."
    effort_level = "Low"

    arn = f"arn:aws:s3:::{bucket_name}"
    policy = "s3-lifecycle-optimization"

    description = (
        f"S3 Bucket {bucket_name} currently has no lifecycle configuration attached. "
        f"All objects in this bucket will remain in their uploaded storage class indefinitely, leading to unnecessary storage costs."
    )

    return {
        "title": "S3 Lifecycle Policy Optimization",
        "category": "Storage & Volumes",
        "accountId": account_id,
        "region": "global",
        "resourceId": bucket_name,
        "resourceArn": arn,
        "service": "S3",
        "type": "Cost Optimization",
        "policy": policy,
        "effortLevel": effort_level,
        "status": status_text,
        "recommendation": recommendation,
        "description": description,
        "bucketName": bucket_name,
        "currentDailyCost": "To be updated",
        "currentMonthlyCost": "To be updated",
        "estimatedMonthlySavings": 0 # Explicitly zero
    }

def main():
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Starting FinOps Policy: S3 Lifecycle Optimization")
    
    s3, sts = create_clients()
    account_id = get_account_id(sts)
    
    logger.info("Fetching S3 buckets and inspecting lifecycle configurations...")
    unoptimized_buckets = fetch_buckets_without_lifecycle(s3)
    
    all_findings = []
    for bucket_name in unoptimized_buckets:
        all_findings.append(build_bucket_finding(bucket_name, account_id))
        
    logger.info(f"Found {len(unoptimized_buckets)} buckets without lifecycle policies.")

    # Pricing Logic
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from pricing_rules import s3_lifecycle_optimization_pricing
        
        pricing_inputs = []
        for finding in all_findings:
            pricing_inputs.append({
                "resource_id": finding["resourceId"]
            })
                
        if pricing_inputs:
            logger.info("Executing pricing calculations...")
            enriched_pricing = s3_lifecycle_optimization_pricing.calculate_savings(pricing_inputs, account_id=account_id)
            pricing_map = {p['resource_id']: p for p in enriched_pricing}
            
            for finding in all_findings:
                if finding["resourceId"] in pricing_map:
                    p_data = pricing_map[finding["resourceId"]]
                    finding["currentDailyCost"] = p_data.get("currentDailyCost", "To be updated")
                    finding["currentMonthlyCost"] = p_data.get("currentMonthlyCost", "To be updated")
                    finding["estimatedMonthlySavings"] = p_data.get("estimatedMonthlySavings", 0)
    except ImportError as e:
        logger.warning(f"Pricing module not found. Skipping pricing calculation. {e}")
    except Exception as e:
        logger.error(f"Failed to execute pricing logic: {e}")
            
    export_to_excel(all_findings, "s3_lifecycle_optimization_report.xlsx")
    
    logger.info(f"\n==================================================")
    logger.info("SCAN COMPLETED")
    logger.info(f"Total Optimization Opportunities Found: {len(all_findings)}")
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
