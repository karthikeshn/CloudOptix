import asyncio
import logging
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.control.control_resource import ControlResource
from app.models.config.config_cloud_account import ConfigCloudAccount
from app.monitoring.base_monitor import monitor_resource_transition
from app.services.aws.discovery.dynamic_discovery import discover_and_upsert_child_ec2
from app.services.aws.session import AWSSessionManager
from app.core.security import decrypt_credentials

logger = logging.getLogger(__name__)

async def run_asg_flow(account_name: str, region: str, resource_id: str, target_state: str):
    """
    Orchestrates the ASG -> EC2 flow.
    1. Waits for ASG to reach target_state.
    2. If RUNNING: Discovers new EC2 instances and tracks them to RUNNING.
    3. If STOPPED: Queries DB for existing EC2 instances, sets to TERMINATING, and tracks to TERMINATED.
    """
    logger.info(f"[ASG Flow] Starting flow for ASG {resource_id} -> {target_state}")
    
    # 1. Wait for ASG
    await monitor_resource_transition(account_name, region, "ASG", resource_id, target_state)
    
    async with SessionLocal() as db:
        stmt = select(ConfigCloudAccount).where(ConfigCloudAccount.account_name == account_name)
        res = await db.execute(stmt)
        config = res.scalars().first()
        if not config:
            return
            
        creds = decrypt_credentials(config.encrypted_credentials)
        session_manager = AWSSessionManager()
        aws_session = session_manager.create_session(creds, region)
        
        # 2. Handle EC2 children
        if target_state.upper() == 'RUNNING':
            logger.info(f"[ASG Flow] ASG is RUNNING. Discovering child EC2s...")
            await discover_and_upsert_child_ec2(
                session=db,
                aws_session=aws_session,
                account_name=account_name,
                region=region,
                parent_service_type="ASG",
                parent_resource_id=resource_id
            )
            
            # The discovery script already inserts them. Let's find them and track them.
            # Usually dynamic discovery waits for them to be running internally, or at least inserts them.
            # We will spawn a tracker for each EC2 to ensure their UI state updates perfectly.
            ec2_stmt = select(ControlResource).where(ControlResource.parent_resource_id == resource_id)
            ec2_res = await db.execute(ec2_stmt)
            ec2s = ec2_res.scalars().all()
            for ec2 in ec2s:
                if ec2.status.upper() not in ['RUNNING', 'TERMINATED', 'SHUTTING-DOWN']:
                    asyncio.create_task(
                        monitor_resource_transition(account_name, region, "EC2", ec2.resource_id, 'RUNNING')
                    )
                    
        elif target_state.upper() == 'STOPPED':
            logger.info(f"[ASG Flow] ASG is STOPPED. Tracking child EC2s to TERMINATED...")
            ec2_stmt = select(ControlResource).where(ControlResource.parent_resource_id == resource_id)
            ec2_res = await db.execute(ec2_stmt)
            ec2s = ec2_res.scalars().all()
            
            for ec2 in ec2s:
                if ec2.status.upper() not in ['TERMINATED', 'SHUTTING-DOWN']:
                    ec2.status = 'TERMINATING'
                    asyncio.create_task(
                        monitor_resource_transition(account_name, region, "EC2", ec2.resource_id, 'TERMINATED')
                    )
            await db.commit()
