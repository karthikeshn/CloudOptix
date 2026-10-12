import os
import boto3

def seed_orphaned_snapshot(endpoint_url="http://localhost:5000"):
    """
    Connects to the persistent Moto server and plants a realistic orphaned snapshot:
    1. Creates an active EBS volume.
    2. Takes a snapshot of it (100 GiB).
    3. Deletes the volume so the snapshot becomes completely orphaned.
    """
    print(f"[Seeder] Connecting to Moto at {endpoint_url}...")
    ec2 = boto3.client(
        'ec2',
        region_name='us-east-1',
        endpoint_url=endpoint_url,
        aws_access_key_id='testing',
        aws_secret_access_key='testing'
    )
    
    # 1. Create Temporary Volume
    vol = ec2.create_volume(
        AvailabilityZone='us-east-1a',
        Size=100,
        VolumeType='gp3'
    )
    vol_id = vol['VolumeId']
    print(f"[Seeder] Created temporary volume: {vol_id}")
    
    # 2. Take Snapshot
    snap = ec2.create_snapshot(
        VolumeId=vol_id,
        Description="Orphaned Snapshot Seeded by Moto Mock Environment"
    )
    snap_id = snap['SnapshotId']
    print(f"[Seeder] Created snapshot: {snap_id} (100 GiB)")
    
    # 3. Delete Volume to make it an orphan
    ec2.delete_volume(VolumeId=vol_id)
    print(f"[Seeder] Deleted volume {vol_id} -> {snap_id} is now an ORPHAN!")
    
    return snap_id

if __name__ == '__main__':
    seed_orphaned_snapshot()
