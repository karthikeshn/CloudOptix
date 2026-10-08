import boto3
import pandas as pd
from datetime import datetime, timezone
import sys
import os

# Ensure utils is importable
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from scripts.delete_stopped_rds_pricing import calculate_savings

def fetch_resources(client, region_name):
    instances = []
    paginator = client.get_paginator('describe_db_instances')
    for page in paginator.paginate():
        instances.extend(page.get('DBInstances', []))
    return instances

def evaluate_resource(resource, account_id, region_name):
    state = resource.get('DBInstanceStatus')
    if state != 'stopped':
        return None
        
    instance_id = resource.get('DBInstanceIdentifier')
    instance_arn = resource.get('DBInstanceArn')
    engine = resource.get('Engine')
    allocated_storage = resource.get('AllocatedStorage', 0)
    
    return {
        'account_id': account_id,
        'region': region_name,
        'resource_id': instance_id,
        'resource_arn': instance_arn,
        'engine': engine,
        'allocated_storage': allocated_storage
    }

def build_finding(priced_resource):
    return {
        "id": "", 
        "title": "Delete Stopped RDS instances", 
        "category": "Delete Stopped RDS instances", 
        "owner": "", 
        "assignedTo": "", 
        "status": "Pending for Review", 
        "accountId": priced_resource['account_id'], 
        "region": priced_resource['region'], 
        "resourceId": priced_resource['resource_id'], 
        "resourceArn": priced_resource['resource_arn'], 
        "service": "RDS", 
        "type": "RDS Instance", 
        "policy": "Delete Stopped RDS instances", 
        "effortLevel": "Medium", 
        "message": "RDS instance is in stopped state.", 
        "recommendation": "RDS instance is in stopped state. Validate ownership and business requirement before deletion.", 
        "description": f"Engine: {priced_resource['engine']} | StorageGB: {priced_resource['allocated_storage']}", 
        "currentDailyCost": priced_resource['currentDailyCost'], 
        "currentMonthlyCost": priced_resource['currentMonthlyCost'], 
        "estimatedMonthlySavings": priced_resource['estimatedMonthlySavings'], 
        "approvalComments": "", 
        "reasonForRejection": "", 
        "achievedSavingsMonthly": "", 
        "month": ""
    }

def export_to_excel(findings, output_file):
    if not findings:
        print("No findings to export.")
        return
    df = pd.DataFrame(findings)
    df.to_excel(output_file, index=False)
    print(f"Exported {len(findings)} findings to {output_file}")

def main(account_id, role_arn=None):
    region_name = "us-east-1"
    client = boto3.client('rds', region_name=region_name)
    
    raw_resources = fetch_resources(client, region_name)
    
    evaluated_resources = []
    for r in raw_resources:
        evaluated = evaluate_resource(r, account_id, region_name)
        if evaluated:
            evaluated_resources.append(evaluated)
            
    priced_resources = calculate_savings(evaluated_resources, account_id)
    
    findings = []
    for pr in priced_resources:
        findings.append(build_finding(pr))
        
    export_to_excel(findings, 'output_delete_stopped_rds.xlsx')

if __name__ == "__main__":
    sts = boto3.client('sts', region_name='us-east-1')
    account_id = sts.get_caller_identity()["Account"]
    main(account_id)
