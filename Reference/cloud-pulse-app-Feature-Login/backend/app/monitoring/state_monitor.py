import asyncio
import logging
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.control.control_resource import ControlResource
from app.monitoring.base_monitor import monitor_resource_transition
from app.monitoring.flow.asg_flow import run_asg_flow
from app.monitoring.flow.ecs_flow import run_ecs_flow
from app.monitoring.flow.eks_flow import run_eks_flow
from app.monitoring.flow.beanstalk_flow import run_beanstalk_flow

logger = logging.getLogger(__name__)

async def route_transition(
    account_name: str,
    region: str,
    service_type: str,
    resource_id: str,
    target_state: str,
    timeout_seconds: int = 900
):
    """
    Main orchestration router. Routes to the appropriate flow based on service type.
    """
    if service_type.upper() == 'ECS':
        await run_ecs_flow(account_name, region, resource_id, target_state)
    elif service_type.upper() == 'EKS':
        await run_eks_flow(account_name, region, resource_id, target_state)
    elif service_type.upper() == 'BEANSTALK':
        await run_beanstalk_flow(account_name, region, resource_id, target_state)
    elif service_type.upper() == 'ASG':
        await run_asg_flow(account_name, region, resource_id, target_state)
    else:
        # Fallback to standard base tracking for un-orchestrated resources
        await monitor_resource_transition(account_name, region, service_type, resource_id, target_state, timeout_seconds)

async def recover_orphaned_transitions():
    try:
        async with SessionLocal() as db:
            stmt = select(ControlResource).where(ControlResource.status.in_(['STARTING', 'STOPPING']))
            res = await db.execute(stmt)
            orphaned = res.scalars().all()
            for r in orphaned:
                target_state = 'RUNNING' if r.status == 'STARTING' else 'STOPPED'
                logger.info(f"[Recovery] Resuming orphaned state monitor for {r.resource_id} (Target: {target_state})")
                svc_type = r.service_type.value if hasattr(r.service_type, 'value') else r.service_type
                asyncio.create_task(
                    route_transition(
                        account_name=r.account_name,
                        region=r.region,
                        service_type=svc_type,
                        resource_id=r.resource_id,
                        target_state=target_state
                    )
                )
    except Exception as e:
        logger.error(f"[Recovery] Failed to recover orphaned transitions: {e}")
