import asyncio
import logging
import json
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.control.control_resource import ControlResource
from app.monitoring.base_monitor import monitor_resource_transition
from app.monitoring.flow.asg_flow import run_asg_flow

logger = logging.getLogger(__name__)

async def run_ecs_flow(account_name: str, region: str, resource_id: str, target_state: str):
    """
    Orchestrates the ECS -> ASG -> EC2 flow.
    1. Waits for ECS to reach target_state.
    2. Reads the ASG name from the ECS config.
    3. Delegates to the ASG flow to handle the rest of the chain.
    """
    logger.info(f"[ECS Flow] Starting flow for ECS {resource_id} -> {target_state}")
    
    # 1. Wait for ECS
    await monitor_resource_transition(account_name, region, "ECS", resource_id, target_state)
    
    # 2. Extract ASG
    async with SessionLocal() as db:
        stmt = select(ControlResource).where(ControlResource.resource_id == resource_id)
        res = await db.execute(stmt)
        ecs_sched = res.scalars().first()
        
        if ecs_sched and ecs_sched.saved_config_json:
            try:
                config_data = json.loads(ecs_sched.saved_config_json)
                asg_name = config_data.get('asg_name')
                if asg_name:
                    logger.info(f"[ECS Flow] ECS reached target. Delegating to ASG Flow for {asg_name}")
                    # Spawn the ASG flow in the background
                    asyncio.create_task(
                        run_asg_flow(account_name, region, asg_name, target_state)
                    )
            except Exception as e:
                logger.error(f"[ECS Flow] Failed to parse config for {resource_id}: {e}")
