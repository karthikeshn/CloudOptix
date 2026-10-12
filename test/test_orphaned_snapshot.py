import os
import zipfile
import csv
import boto3
from moto import mock_aws
import sys
import unittest.mock

# ==============================================================================
# 1. ENVIRONMENT HIJACKING (SMOKE & MIRRORS)
# ==============================================================================
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["DATABASE_URL"] = "sqlite:///d:/FinOpsDashboard/backend/data/test_finops.db"
os.environ["DATABASE_PATH"] = "d:/FinOpsDashboard/backend/data/test_finops.db"

mock_id = os.environ.get("MOCK_AWS_ACCOUNT_ID", "123456789012")
os.environ["MOTO_ACCOUNT_ID"] = mock_id

backend_dir = r"d:\FinOpsDashboard\backend"
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

# ==============================================================================
# 2. FAKE CUR DATA GENERATOR
# ==============================================================================
CUR_DIR = r"d:\FinOpsDashboard\Cur report"
mock_csv_path = os.path.join(CUR_DIR, "mock_snapshot.csv")
mock_zip_path = os.path.join(CUR_DIR, "mock_snapshot.csv.zip")

def setup_fake_cur(resource_id: str, cost: float):
    """Creates a temporary fake AWS CUR zip file specifically for this test."""
    if not os.path.exists(CUR_DIR):
        os.makedirs(CUR_DIR)
        
    with open(mock_csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['lineItem/ResourceId', 'lineItem/UnblendedCost', 'product/region', 'product/ProductName'])
        writer.writerow([resource_id, str(cost), 'us-east-1', 'Amazon Elastic Compute Cloud'])
        
    with zipfile.ZipFile(mock_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(mock_csv_path, os.path.basename(mock_csv_path))

def cleanup_fake_cur():
    """Removes the fake CUR zip file so it doesn't pollute future tests."""
    if os.path.exists(mock_csv_path): os.remove(mock_csv_path)
    if os.path.exists(mock_zip_path): os.remove(mock_zip_path)

# ==============================================================================
# 3. MOTO TEST EXECUTION BLOCK
# ==============================================================================
def test_orphaned_snapshot():
    print("=" * 75)
    print("[PHASE 1] Booting up isolated Moto testing environment for OrphanedSnapshots...")
    print("=" * 75)
    
    # Clear cur_processor cache so freshly injected CUR data is read
    from utils import cur_processor
    cur_processor._cached_df = None

    # Start Moto firewall
    mock = mock_aws()
    mock.start()

    try:
        ec2 = boto3.client('ec2', region_name='us-east-1')
        
        print("\n[Moto] Scenario Setup:")
        print("  1. Creating an Active EBS Volume (vol-1)...")
        vol1 = ec2.create_volume(
            AvailabilityZone='us-east-1a',
            Size=20,
            VolumeType='gp3'
        )
        vol1_id = vol1['VolumeId']
        
        print(f"  2. Creating a VALID snapshot attached to {vol1_id} (Should NOT be flagged)...")
        snap_valid = ec2.create_snapshot(
            VolumeId=vol1_id,
            Description="Valid active snapshot"
        )
        snap_valid_id = snap_valid['SnapshotId']
        
        print("  3. Creating a Temporary Volume to generate an ORPHANED snapshot...")
        vol_temp = ec2.create_volume(
            AvailabilityZone='us-east-1a',
            Size=100,
            VolumeType='gp3'
        )
        vol_temp_id = vol_temp['VolumeId']
        
        snap_orphan = ec2.create_snapshot(
            VolumeId=vol_temp_id,
            Description="Orphan candidate snapshot"
        )
        snap_orphan_id = snap_orphan['SnapshotId']
        
        print(f"  4. DELETING Temporary Volume {vol_temp_id} so {snap_orphan_id} becomes ORPHANED!")
        ec2.delete_volume(VolumeId=vol_temp_id)
        
        # Inject exact fake CUR cost of $7.50 for the orphaned snapshot
        print(f"\n[System] Injecting fake CUR billing record: {snap_orphan_id} -> $7.50 / month...")
        setup_fake_cur(snap_orphan_id, 7.50)
        
        print("\n[System] Fake AWS Infrastructure & CUR data staged.")
        print("[System] Executing OrphanedSnapshot.py with Pricing API Breakout...\n")
        
        # Moto Pause Hack: Temporarily disable Moto while Pricing API is queried over internet
        from pricing_rules import orphaned_snapshot_pricing
        original_get_price = orphaned_snapshot_pricing.get_real_snapshot_market_price
        
        def wrapped_get_price(*args, **kwargs):
            print("\n[System] >>> PAUSING Moto Firewall for Live AWS Pricing API...")
            mock.stop()
            try:
                rate = original_get_price(*args, **kwargs)
                print(f"[System] <<< Live AWS Pricing API returned market rate: ${rate:.2f}/month")
                return rate
            finally:
                mock.start()
                print("[System] >>> Moto Firewall RESTORED.\n")

        with unittest.mock.patch('pricing_rules.orphaned_snapshot_pricing.get_real_snapshot_market_price', side_effect=wrapped_get_price):
            from scripts import OrphanedSnapshot
            OrphanedSnapshot.main(account_id=mock_id)
            
        print("\n" + "=" * 75)
        print("[PHASE 2] Validating Database Tickets in test_finops.db...")
        print("=" * 75)
        
        from core.database import SessionLocal
        from models import Ticket
        import json
        
        db = SessionLocal()
        try:
            tickets = db.query(Ticket).filter(Ticket.script_name == "OrphanedSnapshot").all()
            print(f"Found {len(tickets)} OrphanedSnapshot ticket(s) in test_finops.db:")
            
            for t in tickets:
                details = json.loads(t.details)
                print(f"  - Ticket ID: {t.id}")
                print(f"    Resource ID: {t.resource_id}")
                print(f"    Status: {t.status}")
                print(f"    Potential Savings: ${t.potential_savings}")
                print(f"    Created At: {t.created_at}")
                print(f"    Recommended Action: {t.recommended_action}")
                print(f"    Snapshot Size: {details.get('sizeGiB')} GiB")
                print(f"    Current Monthly Cost: {details.get('currentMonthlyCost')}")
                
            # Assertions
            orphan_ids = [t.resource_id for t in tickets]
            assert snap_orphan_id in orphan_ids, f"Expected {snap_orphan_id} to be flagged as orphaned!"
            assert snap_valid_id not in orphan_ids, f"Valid snapshot {snap_valid_id} should NOT be flagged!"
            print("\n[SUCCESS] Test Passed 100%! All FinOps rules, Pricing API breakout, and DB persistence verified.")
            
        finally:
            db.close()

    finally:
        print("\n[System] Cleaning up mock CUR and tearing down Moto environment...")
        cleanup_fake_cur()
        mock.stop()

if __name__ == '__main__':
    test_orphaned_snapshot()
