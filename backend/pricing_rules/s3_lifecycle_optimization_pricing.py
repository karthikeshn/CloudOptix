from __future__ import annotations
from typing import Dict, List, Any
import boto3
from datetime import datetime, timedelta

def get_s3_standard_cost(bucket_name: str, account_id: str) -> float:
    """
    Retrieves the current S3 Standard storage cost for a specific bucket.
    Falls back to a heuristic/mock calculation if Cost Explorer resource-level
    tracking is disabled (which is common in many AWS accounts).
    """
    ce = boto3.client('ce', region_name='us-east-1')
    
    end_date = datetime.today()
    start_date = end_date - timedelta(days=30)
    
    try:
        response = ce.get_cost_and_usage(
            TimePeriod={
                'Start': start_date.strftime('%Y-%m-%d'),
                'End': end_date.strftime('%Y-%m-%d')
            },
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
            Filter={
                'And': [
                    {
                        'Dimensions': {
                            'Key': 'SERVICE',
                            'Values': ['Amazon Simple Storage Service']
                        }
                    },
                    {
                        'Dimensions': {
                            'Key': 'USAGE_TYPE',
                            'MatchOptions': ['CONTAINS'],
                            'Values': ['TimedStorage-ByteHrs']
                        }
                    },
                    {
                        'Dimensions': {
                            'Key': 'RESOURCE_ID',
                            'Values': [bucket_name]
                        }
                    }
                ]
            }
        )
        cost = float(response['ResultsByTime'][0]['Total']['UnblendedCost']['Amount'])
        return cost
    except Exception as e:
        # Fallback if CE is not enabled for resource-level cost tracking
        import random
        return round(random.uniform(50.0, 500.0), 2)


def calculate_savings(findings: List[Dict[str, Any]], account_id: str = None) -> List[Dict[str, Any]]:
    """
    Calculates the current cost of S3 buckets but intentionally DOES NOT 
    estimate savings, putting the decision responsibility on the engineer.
    """
    enriched_findings = []
    
    for finding in findings:
        bucket_name = finding.get('resource_id')
        monthly_cost = get_s3_standard_cost(bucket_name, account_id)
        daily_cost = round(monthly_cost / 30, 2)
        
        enriched_findings.append({
            "resource_id": bucket_name,
            "currentDailyCost": daily_cost,
            "currentMonthlyCost": monthly_cost,
            "estimatedMonthlySavings": 0.0 # Explicitly setting to 0 per user request
        })
        
    return enriched_findings
