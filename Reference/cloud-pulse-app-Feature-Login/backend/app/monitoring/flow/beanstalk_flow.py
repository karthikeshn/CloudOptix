import asyncio
import logging
import json
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.control.control_resource import ControlResource
from app.monitoring.base_monitor import monitor_resource_transition
from app.monitoring.flow.asg_flow import run_asg_flow

logger = logging.getLogger(__name__)

async def run_beanstalk_flow(account_name: str, region: str, resource_id: str, target_state: str):
    """
    Orchestrates the BEANSTALK -> ASG -> EC2 flow.
    1. Waits for Beanstalk Environment to reach target_state.
    2. Reads the managed ASG name from the Beanstalk config (if any).
    3. Delegates to the ASG flow to handle the rest of the chain.
    """
    logger.info(f"[Beanstalk Flow] Starting flow for Beanstalk {resource_id} -> {target_state}")
    
    # 1. Wait for Beanstalk Environment
    await monitor_resource_transition(account_name, region, "BEANSTALK", resource_id, target_state)
    
    # 2. Extract ASG
    async with SessionLocal() as db:
        stmt = select(ControlResource).where(ControlResource.resource_id == resource_id)
        res = await db.execute(stmt)
        beanstalk_sched = res.scalars().first()
        
        if beanstalk_sched and beanstalk_sched.saved_config_json:
            try:
                config_data = json.loads(beanstalk_sched.saved_config_json)
                
                asg_name = config_data.get('asg_name')
                if asg_name:
                    logger.info(f"[Beanstalk Flow] Beanstalk reached target. Delegating to ASG Flow for ASG {asg_name}")
                    asyncio.create_task(
                        run_asg_flow(account_name, region, asg_name, target_state)
                    )
            except Exception as e:
                logger.error(f"[Beanstalk Flow] Failed to parse config for {resource_id}: {e}")
