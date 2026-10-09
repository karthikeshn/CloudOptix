import boto3
import sys
import os

# Ensure backend directory is importable
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from scripts.delete_stopped_rds_pricing import calculate_savings
from core.database import SessionLocal
from models import Ticket, CloudConfig

def fetch_resources(client):
    """Scans AWS for all RDS instances using standard boto3."""
    instances = []
    paginator = client.get_paginator('describe_db_instances')
    for page in paginator.paginate():
        instances.extend(page.get('DBInstances', []))
    return instances

def evaluate_resource(resource, account_id, region_name):
    """FinOps Rule: If the RDS instance is stopped, it is wasting money on storage."""
    state = resource.get('DBInstanceStatus')
    
    # RULE: Must be stopped
    if state != 'stopped':
        return None
        
    instance_id = resource.get('DBInstanceIdentifier')
    instance_arn = resource.get('DBInstanceArn')
    engine = resource.get('Engine')
    allocated_storage = resource.get('AllocatedStorage', 0)
    storage_type = resource.get('StorageType', 'gp2')
    
    # CRITICAL: We capture the exact parameters needed for Pricing API/CUR
    return {
        'account_id': account_id,
        'region': region_name,
        'resource_id': instance_arn, # CUR uses the ARN for RDS!
        'instance_name': instance_id,
        'engine': engine,
        'allocated_storage': allocated_storage,
        'storage_type': storage_type
    }

def save_to_database(findings):
    """Saves the calculated findings directly into the SQLite database."""
    if not findings:
        print("No stopped RDS instances found. You are fully optimized!")
        return
        
    db = SessionLocal()
    try:
        # Get or create a dummy cloud config for the test account
        account_id_str = findings[0]['account_id']
        account = db.query(CloudConfig).filter(CloudConfig.aws_account_id == account_id_str).first()
        if not account:
            account = CloudConfig(aws_account_id=account_id_str, provider="AWS", account_name="Test Account")
            db.add(account)
            db.commit()
            db.refresh(account)

        import json
        from datetime import datetime
        for finding in findings:
            ticket = Ticket(
                script_name="Delete Stopped RDS instances",
                account_id=account.id,
                resource_id=finding.get('resource_id', 'unknown'),
                potential_savings=str(finding.get('estimatedMonthlySavings', '').replace('$', '')),
                status="Pending",
                details=json.dumps(finding),
                recommended_action="Delete stopped instance to stop paying for unused storage.",
                created_at=datetime.utcnow().isoformat() + "Z"
            )
            db.add(ticket)
        db.commit()
        print(f"Successfully saved {len(findings)} FinOps tickets to the database!")
    except Exception as e:
        print(f"Database error: {e}")
    finally:
        db.close()

def main(account_id):
    # 1. Fetch all active AWS regions dynamically
    base_ec2 = boto3.client('ec2', region_name='us-east-1')
    try:
        regions_response = base_ec2.describe_regions()
        regions = [r["RegionName"] for r in regions_response.get("Regions", [])]
    except Exception as e:
        print(f"Failed to fetch regions: {e}")
        regions = ["us-east-1"] # Fallback
        
    evaluated_resources = []
    
    # 2. Scan every region for stopped RDS instances
    for region_name in regions:
        print(f"Scanning region: {region_name}...")
        try:
            client = boto3.client('rds', region_name=region_name)
            raw_resources = fetch_resources(client)
            
            # 3. Evaluate FinOps Rules
            for r in raw_resources:
                evaluated = evaluate_resource(r, account_id, region_name)
                if evaluated:
                    evaluated_resources.append(evaluated)
        except Exception as e:
            print(f"Failed to scan region {region_name}: {e}")
            
    if not evaluated_resources:
        print("No violating resources found in any region.")
        return
        
    # 4. Hand off to Pricing Engine (Phase 3)
    priced_resources = calculate_savings(evaluated_resources, account_id)
    
    # 5. Save Tickets to Database
    save_to_database(priced_resources)

if __name__ == "__main__":
    # If run in production, pull the real AWS account ID
    sts = boto3.client('sts', region_name='us-east-1')
    try:
        real_account_id = sts.get_caller_identity()["Account"]
    except Exception:
        real_account_id = "123456789012"
    main(real_account_id)
