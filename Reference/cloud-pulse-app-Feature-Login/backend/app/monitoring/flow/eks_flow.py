import asyncio
import logging
import json
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.control.control_resource import ControlResource
from app.monitoring.base_monitor import monitor_resource_transition
from app.monitoring.flow.asg_flow import run_asg_flow

logger = logging.getLogger(__name__)

async def run_eks_flow(account_name: str, region: str, resource_id: str, target_state: str):
    """
    Orchestrates the EKS -> ASG -> EC2 flow.
    1. Waits for EKS Managed Node Group to reach target_state.
    2. Reads the unmanaged ASG names from the EKS config (if any).
    3. Delegates to the ASG flow to handle the rest of the chain.
    """
    logger.info(f"[EKS Flow] Starting flow for EKS {resource_id} -> {target_state}")
    
    # 1. Wait for EKS Managed Node Group
    await monitor_resource_transition(account_name, region, "EKS", resource_id, target_state)
    
    # 2. Extract ASGs
    async with SessionLocal() as db:
        stmt = select(ControlResource).where(ControlResource.resource_id == resource_id)
        res = await db.execute(stmt)
        eks_sched = res.scalars().first()
        
        if eks_sched and eks_sched.saved_config_json:
            try:
                config_data = json.loads(eks_sched.saved_config_json)
                unmanaged_asgs = config_data.get('unmanaged_asgs', [])
                
                for asg in unmanaged_asgs:
                    asg_name = asg.get('name')
                    if asg_name:
                        logger.info(f"[EKS Flow] EKS reached target. Delegating to ASG Flow for unmanaged ASG {asg_name}")
                        # Spawn the ASG flow in the background
                        asyncio.create_task(
                            run_asg_flow(account_name, region, asg_name, target_state)
                        )
                
                # 3. Trigger ASG Flow for the managed ASG if it exists
                managed_asg_name = config_data.get('asg_name')
                if managed_asg_name:
                    logger.info(f"[EKS Flow] EKS reached target. Delegating to ASG Flow for managed ASG {managed_asg_name}")
                    asyncio.create_task(
                        run_asg_flow(account_name, region, managed_asg_name, target_state)
                    )
            except Exception as e:
                logger.error(f"[EKS Flow] Failed to parse config for {resource_id}: {e}")
