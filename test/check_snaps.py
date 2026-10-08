import boto3
import sys
import os

# Setup path for pricing script
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from pricing_rules import orphaned_snapshot_pricing

def main():
    sts = boto3.client('sts', region_name='us-east-1')
    account_id = sts.get_caller_identity()["Account"]

    for region in ['us-east-1', 'us-west-2']:
        try:
            ec2 = boto3.client('ec2', region_name=region)
            response = ec2.describe_snapshots(OwnerIds=['self'])
            snapshots = response.get('Snapshots', [])
            print(f"Region {region}: {len(snapshots)} snapshots found.")
            
            if not snapshots:
                continue

            pricing_inputs = []
            for snap in snapshots:
                pricing_inputs.append({
                    "resource_id": snap['SnapshotId'],
                    "region": region,
                    "size_gb": snap.get('VolumeSize', 0)
                })
                
            enriched_pricing = orphaned_snapshot_pricing.calculate_savings(pricing_inputs, account_id=account_id)
            
            for snap, price_data in zip(snapshots, enriched_pricing):
                print(f"  - {snap['SnapshotId']} | VolumeId: {snap.get('VolumeId', 'N/A')} | Size: {snap.get('VolumeSize')} GiB")
                print(f"      Monthly Cost: {price_data.get('currentMonthlyCost')} | Daily Cost: {price_data.get('currentDailyCost')}")
                    
        except Exception as e:
            print(f"Failed to check region {region}: {e}")

if __name__ == "__main__":
    main()
