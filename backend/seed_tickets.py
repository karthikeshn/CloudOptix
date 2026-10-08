import os
import sys
import json
from datetime import datetime

# Setup path so we can import from backend modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.database import SessionLocal, engine
import models

def seed_tickets():
    db = SessionLocal()
    
    # Ensure tables exist
    models.Base.metadata.create_all(bind=engine)
    
    # Check if tickets already exist
    existing = db.query(models.Ticket).count()
    if existing > 0:
        print(f"Database already has {existing} tickets. Skipping seed.")
        db.close()
        return

    now_iso = datetime.utcnow().isoformat() + "Z"
    
    mock_tickets = [
        # Pending Tickets
        models.Ticket(
            script_name="find_unattached_ebs.py",
            account_id=1,
            resource_id="vol-0abcd1234efgh5678",
            potential_savings="20.00",
            status="Pending",
            details=json.dumps({"VolumeType": "gp3", "SizeGB": 100, "State": "available", "Region": "us-east-1", "Created": "2023-01-15"}),
            created_at=now_iso
        ),
        models.Ticket(
            script_name="find_unattached_ebs.py",
            account_id=1,
            resource_id="vol-0f0f0f0f0f0f0f0f0",
            potential_savings="5.00",
            status="Pending",
            details=json.dumps({"VolumeType": "gp2", "SizeGB": 50, "State": "available", "Region": "us-east-1", "Created": "2023-04-22"}),
            created_at=now_iso
        ),
        models.Ticket(
            script_name="idle_rds_instances.py",
            account_id=1,
            resource_id="db-XYZ123ABC",
            potential_savings="150.00",
            status="Pending",
            details=json.dumps({"Engine": "postgres", "Class": "db.m5.large", "AvgCPU": "0.5%", "Connections": "0", "Region": "us-east-1"}),
            created_at=now_iso,
            recommended_action="Stop Resource"
        ),
        # Approved Tickets
        models.Ticket(
            script_name="old_snapshots.py",
            account_id=1,
            resource_id="snap-0987654321fedcba",
            potential_savings="12.50",
            status="Approved",
            details=json.dumps({"AgeDays": 400, "SizeGB": 250, "Encrypted": "True", "Description": "Old backup"}),
            created_at=now_iso,
            recommended_action="Delete Resource"
        ),
        # Rejected Tickets
        models.Ticket(
            script_name="idle_ec2.py",
            account_id=1,
            resource_id="i-0123456789abcdef0",
            potential_savings="45.00",
            status="Rejected",
            details=json.dumps({"InstanceType": "t3.medium", "AvgCPU": "1.2%", "NetworkIn": "5MB", "Tags": "DisasterRecovery"}),
            created_at=now_iso
        )
    ]
    
    db.add_all(mock_tickets)
    db.commit()
    print(f"Successfully seeded {len(mock_tickets)} mock tickets!")
    db.close()

if __name__ == "__main__":
    seed_tickets()
