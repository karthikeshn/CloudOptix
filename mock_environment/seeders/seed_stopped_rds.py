import os
import boto3

def seed_stopped_rds(endpoint_url="http://localhost:5000"):
    """
    Connects to the persistent Moto server and plants a stopped RDS instance:
    1. Creates a MySQL db.t3.micro RDS instance with 50 GB storage.
    2. Stops the instance so it flags the FinOps rule.
    """
    print(f"[Seeder] Connecting to Moto at {endpoint_url}...")
    rds = boto3.client(
        'rds',
        region_name='us-east-1',
        endpoint_url=endpoint_url,
        aws_access_key_id='testing',
        aws_secret_access_key='testing'
    )
    
    db_id = 'mock-stopped-db-1'
    print(f"[Seeder] Creating RDS instance: {db_id}...")
    try:
        rds.create_db_instance(
            DBInstanceIdentifier=db_id,
            AllocatedStorage=50,
            DBInstanceClass='db.t3.micro',
            Engine='mysql',
            MasterUsername='admin',
            MasterUserPassword='password123'
        )
    except Exception as e:
        print(f"[Seeder] Instance may already exist: {e}")
        
    print(f"[Seeder] Stopping RDS instance: {db_id}...")
    try:
        rds.stop_db_instance(DBInstanceIdentifier=db_id)
        print(f"[Seeder] Successfully stopped {db_id}!")
    except Exception as e:
        print(f"[Seeder] Note on stop: {e}")
        
    return db_id

if __name__ == '__main__':
    seed_stopped_rds()
