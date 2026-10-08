import boto3
import logging
from botocore.config import Config
from botocore.exceptions import ClientError
from datetime import datetime, timezone
import pandas as pd
import json

# ============================================================
# AWS CONFIGURATION
# ============================================================

AWS_CONFIG = Config(
    retries={
        "mode": "adaptive",
        "max_attempts": 10,
    }
)

POLICY_TITLE = "S3 Missing Lifecycle Policy"
POLICY_CATEGORY = "AWS S3 Optimization"
POLICY_SERVICE = "S3"
POLICY_TAG = "FinOps"

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
    
    if isinstance(findings, dict):
        findings = [findings]

    for finding in findings:
        flat_finding = {}
        extra_attributes = []
        
        for key, value in finding.items():
            if isinstance(value, (dict, list)):
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

    df = pd.DataFrame(flat_findings, columns=STANDARD_COLUMNS)
    df.to_excel(filename, index=False)


# ============================================================
# EVALUATE BUCKET
# ============================================================

def evaluate_bucket(s3_client, bucket_name, account_id):
    # Determine region
    region = "us-east-1"
    try:
        location = s3_client.get_bucket_location(Bucket=bucket_name)
        if location and location.get('LocationConstraint'):
            region = location.get('LocationConstraint')
    except ClientError as e:
        logging.warning(f"Could not get location for bucket {bucket_name}: {e}")

    # Check for lifecycle configuration
    has_policy = False
    try:
        s3_client.get_bucket_lifecycle_configuration(Bucket=bucket_name)
        has_policy = True
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code != "NoSuchLifecycleConfiguration":
            logging.warning(f"Error checking lifecycle for bucket {bucket_name}: {e}")

    if has_policy:
        status = "Optimized"
        recommendation = "Bucket has a lifecycle policy. Keep."
        effort_level = "None"
        finding_type = "Has Lifecycle Policy"
        message = f"S3 bucket '{bucket_name}' has an active lifecycle policy."
    else:
        status = "Review Required"
        recommendation = "Create an S3 lifecycle policy to automatically transition or expire old objects to save storage costs."
        effort_level = "Low"
        finding_type = "Missing Lifecycle Policy"
        message = f"S3 bucket '{bucket_name}' does not have a lifecycle policy."

    resource_arn = f"arn:aws:s3:::{bucket_name}"
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")

    description = (
        f"Bucket Name: {bucket_name} | "
        f"Region: {region} | "
        f"Has Policy: {has_policy}"
    )

    return {
        "workItemType": "Task",
        "state": "To Do",
        "id": "",
        "title": POLICY_TITLE,
        "category": POLICY_CATEGORY,
        "owner": "",
        "assignedTo": "",
        "status": status,
        "areaPath": "AWS Cost Optimization",
        "tags": POLICY_TAG,
        "commentCount": 0,
        "accountId": account_id,
        "region": region,
        "resourceNameOrId": bucket_name,
        "resourceId": bucket_name,
        "resourceArn": resource_arn,
        "service": POLICY_SERVICE,
        "type": finding_type,
        "policy": POLICY_TITLE,
        "effortLevel": effort_level,
        "message": message,
        "recommendation": recommendation,
        "description": description,
        "currentDailyCost": "To be updated",
        "currentMonthlyCost": "To be updated",
        "estimatedMonthlySavings": "",
        "approvalComments": "",
        "reasonForRejection": "",
        "achievedSavingsMonthly": "",
        "month": current_month
    }


# ============================================================
# MAIN
# ============================================================

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Starting FinOps Policy: S3 Missing Lifecycle Policy")

    # AWS STS client for Account ID
    try:
        sts_client = boto3.client("sts", config=AWS_CONFIG)
        account_id = sts_client.get_caller_identity()["Account"]
        logger.info(f"AWS Account ID: {account_id}")
    except Exception as e:
        logger.error(f"Failed to fetch AWS Account ID: {e}")
        return

    # S3 Client (Global endpoint)
    try:
        s3_client = boto3.client("s3", config=AWS_CONFIG)
        response = s3_client.list_buckets()
        buckets = response.get("Buckets", [])
    except Exception as e:
        logger.error(f"Failed to fetch S3 buckets: {e}")
        return

    logger.info(f"Discovered {len(buckets)} S3 buckets to evaluate.")

    all_findings = []

    for bucket in buckets:
        bucket_name = bucket["Name"]
        try:
            finding = evaluate_bucket(s3_client, bucket_name, account_id)
            all_findings.append(finding)
        except Exception as e:
            logger.error(f"Failed to evaluate bucket {bucket_name}: {e}")

    logger.info(f"Evaluated {len(buckets)} S3 buckets.")

    # Export findings
    output_file = "s3_missing_lifecycle_policy_report.xlsx"
    export_to_excel(findings=all_findings, filename=output_file)
    logger.info(f"Excel report created: {output_file}")

    # Summary
    logger.info("\n==================================================")
    logger.info("SCAN COMPLETED")
    logger.info(f"Total Buckets Evaluated: {len(buckets)}")
    logger.info(f"Total Findings Exported: {len(all_findings)}")
    logger.info("==================================================")


if __name__ == "__main__":
    main()
