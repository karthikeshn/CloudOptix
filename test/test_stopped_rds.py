import os
import zipfile
import csv
import boto3
from moto import mock_aws
import sys

# ==========================================
# 1. ENVIRONMENT HIJACKING (SMOKE & MIRRORS)
# ==========================================
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["DATABASE_URL"] = "sqlite:///d:/FinOpsDashboard/backend/data/test_finops.db"
os.environ["DATABASE_PATH"] = "d:/FinOpsDashboard/backend/data/test_finops.db"

# Force Moto to use the injected active UI account ID so ARNs match perfectly!
mock_id = os.environ.get("MOCK_AWS_ACCOUNT_ID", "123456789012")
os.environ["MOTO_ACCOUNT_ID"] = mock_id

# We must ensure the backend directory is in the python path
sys.path.append('d:/FinOpsDashboard/backend')

# ==========================================
# 2. FAKE CUR DATA GENERATOR
# ==========================================
CUR_DIR = r"d:\FinOpsDashboard\Cur report"
mock_csv_path = os.path.join(CUR_DIR, "mock_rds.csv")
mock_zip_path = os.path.join(CUR_DIR, "mock_rds.csv.zip")

def setup_fake_cur(resource_arn, cost):
    """Creates a temporary fake AWS CUR zip file specifically for this test."""
    if not os.path.exists(CUR_DIR):
        os.makedirs(CUR_DIR)
        
    with open(mock_csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        # Exact AWS CUR schema columns
        writer.writerow(['lineItem/ResourceId', 'lineItem/UnblendedCost', 'product/region', 'product/ProductName'])
        writer.writerow([resource_arn, str(cost), 'us-east-1', 'Amazon Relational Database Service'])
        
    with zipfile.ZipFile(mock_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(mock_csv_path, os.path.basename(mock_csv_path))

def cleanup_fake_cur():
    """Removes the fake CUR zip file so it doesn't pollute future tests."""
    if os.path.exists(mock_csv_path): os.remove(mock_csv_path)
    if os.path.exists(mock_zip_path): os.remove(mock_zip_path)


# ==========================================
# 3. MOTO EXECUTION BLOCK
# ==========================================
def test_stopped_rds():
    print("[PHASE 1] Booting up isolated testing environment...")
    
    # We clear the cur_processor cache just in case previous tests ran in the same python session
    from utils import cur_processor
    cur_processor._cached_df = None 

    # Start Moto firewall manually so we can control it
    mock = mock_aws()
    mock.start()

    try:
        print("[Moto] Creating a fake RDS instance in RAM...")
        rds_client = boto3.client('rds', region_name='us-east-1')
        
        # Normally this would cost money and take 15 minutes!
        rds_client.create_db_instance(
            DBInstanceIdentifier='fake-stopped-db-1',
            AllocatedStorage=50,
            DBInstanceClass='db.t3.micro',
            Engine='mysql',
            MasterUsername='admin',
            MasterUserPassword='password123'
        )
        
        # Force the state to "stopped" to trigger our FinOps rule
        print("[Moto] Stopping the RDS instance...")
        rds_client.stop_db_instance(DBInstanceIdentifier='fake-stopped-db-1')
        
        # Fetch the selected AWS Account ID from the UI via our injected environment variable!
        selected_account_id = os.environ.get("MOCK_AWS_ACCOUNT_ID", "123456789012")
        
        # The ARN format that AWS CUR expects for RDS instances
        fake_arn = f"arn:aws:rds:us-east-1:{selected_account_id}:db:fake-stopped-db-1"
        
        print(f"[System] Injecting fake CUR data ($45.00 historical cost) for {fake_arn}...")
        setup_fake_cur(fake_arn, 45.00)
        
        print("\n[System] Fake environment perfectly staged. Executing Production Script...\n")
        
        # --- THE MOTO PAUSE HACK ---
        import unittest.mock
        from scripts import delete_stopped_rds_pricing
        original_calc = delete_stopped_rds_pricing.calculate_savings
        
        def wrapped_calc(*args, **kwargs):
            print("\n[System] PAUSING Moto Firewall for Pricing API...")
            mock.stop()
            try:
                return original_calc(*args, **kwargs)
            finally:
                mock.start()
                print("[System] Moto Firewall RESTORED.\n")

        # Patch the pricing engine in memory for just this test
        with unittest.mock.patch('scripts.delete_stopped_rds_pricing.calculate_savings', side_effect=wrapped_calc):
            from scripts import delete_stopped_rds
            delete_stopped_rds.main(selected_account_id)
            
    finally:
        print("[System] Cleaning up fake CUR data and tearing down Moto...")
        cleanup_fake_cur()
        mock.stop()

if __name__ == '__main__':
    test_stopped_rds()
