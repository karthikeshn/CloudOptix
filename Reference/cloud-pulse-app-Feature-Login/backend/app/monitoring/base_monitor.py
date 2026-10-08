import asyncio
import logging
import json
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.config.config_cloud_account import ConfigCloudAccount
from app.models.control.control_resource import ControlResource
from app.models.control.control_action_log import ControlActionLog
from app.services.action_logger import log_control_action
from app.models.system.system_notification import SystemNotification
from app.services.control_service import control_service
from app.core.security import decrypt_credentials

logger = logging.getLogger(__name__)

async def monitor_resource_transition(
    account_name: str,
    region: str,
    service_type: str,
    resource_id: str,
    target_state: str,
    timeout_seconds: int = 900
):
    """
    Polls the AWS live state of a resource until it reaches the target_state (e.g. STOPPED or RUNNING),
    then updates the local database.
    """
    logger.info(f"[State Monitor] Starting tracking for {resource_id} waiting for {target_state}")
    
    elapsed = 0
    poll_interval = 15
    
    async with SessionLocal() as db:
        stmt = select(ConfigCloudAccount).where(ConfigCloudAccount.account_name == account_name)
        res = await db.execute(stmt)
        config = res.scalars().first()
        if not config:
            logger.error(f"[State Monitor] Account {account_name} not found")
            return
            
        creds = decrypt_credentials(config.encrypted_credentials)
        
        while elapsed < timeout_seconds:
            try:
                current_status = await control_service.get_resource_state(
                    config.provider, creds, region, service_type, resource_id
                )
                
                current_status = current_status.upper() if current_status else 'UNKNOWN'
                logger.info(f"[State Monitor] {resource_id} is currently {current_status}")
                
                # Check if target state reached
                # Also handle if target is STOPPED but it got TERMINATED
                if current_status == target_state.upper() or (target_state.upper() == 'STOPPED' and current_status == 'TERMINATED'):
                    # Target reached, update DB!
                    stmt = select(ControlResource).where(ControlResource.resource_id == resource_id)
                    res = await db.execute(stmt)
                    sched = res.scalars().first()
                    
                    if sched:
                        sched.status = current_status if current_status == 'TERMINATED' else target_state.upper()
                        
                        config_data = json.loads(sched.saved_config_json) if sched.saved_config_json else {}
                        action_type = config_data.get('last_action', 'MANUAL START' if target_state.upper() == 'RUNNING' else 'MANUAL STOP')
                        
                        log_control_action(
                            session=db,
                            native_id=sched.resource_id,
                            account_name=sched.account_name,
                            provider=sched.cloud_provider,
                            action_type=action_type,
                            status="SUCCESS",
                            details=f"Resource successfully transitioned to {sched.status}.",
                            resource_name=sched.resource_name,
                            resource_type=sched.service_type
                        )
                        
                        notification = SystemNotification(
                            title="Resource State Changed",
                            message=f"{sched.resource_name} ({sched.resource_id}) has successfully transitioned to {sched.status}.",
                            type="SUCCESS",
                            module="CONTROL"
                        )
                        db.add(notification)
                        
                        await db.commit()
                        logger.info(f"[State Monitor] Successfully updated DB state for {resource_id} to {sched.status}")
                            
                    return
            except Exception as e:
                logger.warning(f"[State Monitor] Error polling {resource_id}: {e}")
                
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            
        logger.warning(f"[State Monitor] Timeout reached while waiting for {resource_id} to reach {target_state}")
