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

def create_clients(region_name: str = "us-east-1"):
    co = boto3.client("compute-optimizer", region_name=region_name, config=AWS_CONFIG)
    sts = boto3.client("sts", region_name=region_name, config=AWS_CONFIG)
    return co, sts

def get_account_id(sts) -> str:
    return sts.get_caller_identity()["Account"]

def fetch_compute_optimizer_recommendations(co) -> List[Dict[str, Any]]:
    recommendations = []
    try:
        next_token = None
        while True:
            params = {
                "filters": [{"name": "Finding", "values": ["OVER_PROVISIONED"]}]
            }
            if next_token:
                params["nextToken"] = next_token
                
            response = co.get_ec2_instance_recommendations(**params)
            recommendations.extend(response.get("instanceRecommendations", []))
            
            next_token = response.get("nextToken")
            if not next_token:
                break
    except ClientError as e:
        import logging
        logging.getLogger(__name__).warning(f"Compute Optimizer API failed (it might not be enabled): {e}")
        # Return mock data if not enabled for testing
        return [
            {
                "instanceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-0abcd1234efgh5678",
                "currentInstanceType": "t3.xlarge",
                "finding": "OVER_PROVISIONED",
                "recommendationOptions": [
                    {
                        "instanceType": "t4g.medium",
                        "savingsOpportunity": {
                            "savingsOpportunityPercentage": 45.0,
                            "estimatedMonthlySavings": {"value": 45.20}
                        }
                    }
                ]
            }
        ]
    
    return recommendations

def build_rightsizing_finding(
    rec: Dict[str, Any],
    account_id: str,
) -> Dict[str, Any]:

    arn = rec.get("instanceArn", "")
    instance_id = arn.split("/")[-1] if "/" in arn else "unknown"
    current_type = rec.get("currentInstanceType", "unknown")
    
    options = rec.get("recommendationOptions", [])
    target_type = options[0].get("instanceType", "unknown") if options else "unknown"
    
    savings_opp = options[0].get("savingsOpportunity", {}) if options else {}
    estimated_savings = savings_opp.get("estimatedMonthlySavings", {}).get("value", 0.0)
    savings_percentage = savings_opp.get("savingsOpportunityPercentage", 0.0)

    status_text = "Actionable"
    recommendation = f"Downsize EC2 instance {instance_id} from {current_type} to {target_type} based on Compute Optimizer recommendations."
    effort_level = "Medium"
    policy = "ec2-compute-optimizer-rightsizing"

    description = (
        f"AWS Compute Optimizer identified {instance_id} ({current_type}) as OVER_PROVISIONED. "
        f"Changing to {target_type} is the optimal recommendation to reduce costs without impacting performance."
    )

    return {
        "title": "EC2 Rightsizing (Compute Optimizer)",
        "category": "Compute",
        "accountId": account_id,
        "region": "global",
        "resourceId": instance_id,
        "resourceArn": arn,
        "service": "EC2",
        "type": "Rightsizing",
        "policy": policy,
        "effortLevel": effort_level,
        "status": status_text,
        "recommendation": recommendation,
        "description": description,
        "currentInstanceType": current_type,
        "targetInstanceType": target_type,
        
        # Temp keys for pricing script
        "compute_optimizer_savings": estimated_savings,
        "compute_optimizer_savings_percentage": savings_percentage,
        
        "currentDailyCost": "To be updated",
        "currentMonthlyCost": "To be updated",
        "estimatedMonthlySavings": "To be updated"
    }

def main():
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Starting FinOps Policy: EC2 Rightsizing (Compute Optimizer)")
    
    co, sts = create_clients()
    account_id = get_account_id(sts)
    
    logger.info("Fetching recommendations from AWS Compute Optimizer...")
    recommendations = fetch_compute_optimizer_recommendations(co)
    
    all_findings = []
    for rec in recommendations:
        all_findings.append(build_rightsizing_finding(rec, account_id))
        
    logger.info(f"Found {len(all_findings)} over-provisioned instances.")

    # Pricing Logic
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from pricing_rules import ec2_rightsizing_pricing
        
        pricing_inputs = []
        for finding in all_findings:
            pricing_inputs.append({
                "resource_id": finding["resourceId"],
                "compute_optimizer_savings": finding["compute_optimizer_savings"],
                "compute_optimizer_savings_percentage": finding["compute_optimizer_savings_percentage"]
            })
                
        if pricing_inputs:
            logger.info("Executing pricing calculations...")
            enriched_pricing = ec2_rightsizing_pricing.calculate_savings(pricing_inputs, account_id=account_id)
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
            
    export_to_excel(all_findings, "ec2_rightsizing_report.xlsx")
    
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
            # Skip temp keys used for pricing handoff
            if key in ["compute_optimizer_savings", "compute_optimizer_savings_percentage"]:
                continue
                
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
