from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models import ControlResource, ConfigCloudAccount, ControlActionLog
from app.core.security import decrypt_credentials
from app.services.control_service import control_service
from app.services.action_logger import log_control_action
from app.repositories.control_repository import control_repository
from app.schemas import ScheduleUpdatePayload, ManualPowerActionPayload, LogActionPayload
from app.monitoring.state_monitor import route_transition

class VisibilityTogglePayload(BaseModel):
    resource_ids: list[str]
    is_visible: bool

router = APIRouter(prefix="/control", tags=["Resource Control"])



@router.get("/schedules")
async def list_schedules(db: AsyncSession = Depends(get_db)):
    return await control_repository.get_all_schedules(db)

@router.get("/summary")
async def get_summary(
    account_name: Optional[str] = None, 
    provider: Optional[str] = None,
    region: Optional[str] = None,
    tag: Optional[str] = None,
    service_type: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    return await control_repository.get_dashboard_summary(db, account_name, provider, region, tag, service_type, status)

@router.get("/resources")
async def list_controllable_resources(
    account_name: Optional[str] = None, 
    provider: Optional[str] = None,
    region: Optional[str] = None,
    tag: Optional[str] = None,
    show_hidden: bool = False,
    limit: int = Query(50),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db)
):
    """Fetch controllable resources along with their current schedule metadata, with backend filtering."""
    return await control_repository.get_filtered_resources(
        db, limit, offset, show_hidden, account_name, provider, region, tag
    )

@router.post("/toggle-visibility")
async def toggle_visibility(payload: VisibilityTogglePayload, db: AsyncSession = Depends(get_db)):
    updated_count = await control_repository.update_visibility(db, payload.resource_ids, payload.is_visible)
    return {"message": f"Updated visibility for {updated_count} resources (including cascaded children)"}

@router.get("/filter-options")
async def get_filter_options(account_name: Optional[str] = None, provider: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    return await control_repository.get_filter_options(db, account_name, provider)



@router.post("/schedule")
async def save_schedule(payload: ScheduleUpdatePayload, db: AsyncSession = Depends(get_db)):
    sched = await db.get(ControlResource, payload.resource_id)
    if not sched:
        raise HTTPException(status_code=404, detail="Resource not found")
    else:
        sched.is_automation_enabled = payload.is_automation_enabled
        sched.disabled_dates = json.dumps(payload.disabled_dates)
        sched.start_time = payload.start_time
        sched.stop_time = payload.stop_time
        sched.timezone = payload.timezone
        sched.account_name = payload.account_name
        sched.region = payload.region
        
    await db.commit()
    
    # Log schedule update
    log_control_action(
        session=db,
        native_id=payload.resource_id,
        account_name=payload.account_name,
        provider=sched.cloud_provider,
        action_type="SCHEDULE_UPDATED",
        status="SUCCESS",
        details=f"Automation {'enabled' if payload.is_automation_enabled else 'disabled'}. Times: {payload.start_time} - {payload.stop_time} ({payload.timezone})",
        resource_name=sched.resource_name,
        resource_type=sched.service_type if sched else None
    )
    await db.commit()
    
    return {"status": "success", "message": "Schedule updated successfully"}

@router.post("/toggle-power")
async def toggle_power(payload: ManualPowerActionPayload, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    stmt = select(ConfigCloudAccount).where(ConfigCloudAccount.account_name == payload.account_name)
    res = await db.execute(stmt)
    config = res.scalars().first()
    if not config:
        raise HTTPException(status_code=404, detail=f"Cloud config for account '{payload.account_name}' not found.")
        
    creds = decrypt_credentials(config.encrypted_credentials)
    
    try:
        # Fetch the resource to check tags and saved_config
        sched_stmt = select(ControlResource).where(ControlResource.resource_id == payload.resource_id)
        sched_res = await db.execute(sched_stmt)
        sched = sched_res.scalars().first()
        
        # Block manual actions on resources natively managed by a parent
        is_valid, err_msg = control_service.validate_resource_hierarchy(sched)
        if not is_valid:
            raise HTTPException(status_code=400, detail=err_msg)

        saved_config = sched.saved_config_json if sched else None

        if payload.action.upper() == 'START':
            res = await control_service.start_resource(config.provider, creds, payload.region, payload.service_type, payload.resource_id, saved_config=saved_config)
        elif payload.action.upper() == 'STOP':
            res = await control_service.stop_resource(config.provider, creds, payload.region, payload.service_type, payload.resource_id, saved_config=saved_config)
        else:
            raise HTTPException(status_code=400, detail="Action must be START or STOP")
            
        is_success = res.get("status") == "success"
        
        if res.get("status") != "success":
            sched_stmt = select(ControlResource).where(ControlResource.resource_id == payload.resource_id)
            sched_res = await db.execute(sched_stmt)
            sched = sched_res.scalars().first()
            
            log_control_action(
                session=db,
                native_id=payload.resource_id,
                account_name=payload.account_name,
                provider=config.provider,
                action_type="MANUAL START" if payload.action.upper() == "START" else "MANUAL STOP",
                status="FAILED",
                details=str(res.get("details", res.get("message", ""))),
                resource_name=sched.resource_name if sched else payload.resource_id,
                resource_type=sched.service_type if sched else payload.service_type
            )
            await db.commit()
            
            raise HTTPException(status_code=400, detail=res.get("message"))
            
        # Update database with optimistic transitioning state and saved configs
        if res.get("status") == "success":
            if not sched:
                sched_stmt = select(ControlResource).where(ControlResource.resource_id == payload.resource_id)
                sched_res = await db.execute(sched_stmt)
                sched = sched_res.scalars().first()
            if sched:
                sched.status = "STARTING" if payload.action.upper() == "START" else "STOPPING"
                config_data = json.loads(sched.saved_config_json) if sched.saved_config_json else {}
                
                # If the action returned a new config (e.g. STOP), merge it
                if res.get("saved_config_json"):
                    new_config = json.loads(res["saved_config_json"])
                    config_data.update(new_config)
                    
                # Automatically update the associated ASG state in the local DB
                if config_data.get("asg_name"):
                    asg_stmt = select(ControlResource).where(ControlResource.resource_id == config_data["asg_name"])
                    asg_res = await db.execute(asg_stmt)
                    asg_sched = asg_res.scalars().first()
                    if asg_sched:
                        asg_sched.status = "STARTING" if payload.action.upper() == "START" else "STOPPING"
                        asg_config = json.loads(asg_sched.saved_config_json) if asg_sched.saved_config_json else {}
                        asg_config['last_action'] = "MANUAL START" if payload.action.upper() == "START" else "MANUAL STOP"
                        asg_sched.saved_config_json = json.dumps(asg_config)
                            
                config_data['last_action'] = "MANUAL START" if payload.action.upper() == "START" else "MANUAL STOP"
                sched.saved_config_json = json.dumps(config_data)
                
                await db.commit()
                
                # Spawn background monitoring task for the main resource (router will handle the flow)
                target_state = "RUNNING" if payload.action.upper() == "START" else "STOPPED"
                background_tasks.add_task(
                    route_transition,
                    account_name=payload.account_name,
                    region=payload.region,
                    service_type=payload.service_type,
                    resource_id=payload.resource_id,
                    target_state=target_state
                )
            
        return res
    except Exception as e:
        log_control_action(
            session=db,
            native_id=payload.resource_id,
            account_name=payload.account_name,
            provider=config.provider,
            action_type="MANUAL START" if payload.action.upper() == "START" else "MANUAL STOP",
            status="FAILED",
            details=str(getattr(e, 'detail', str(e))),
            resource_name=sched.resource_name if sched else payload.resource_id,
            resource_type=sched.service_type if sched else payload.service_type
        )
        await db.commit()
        raise e

@router.get("/audit-logs")
async def list_audit_logs(
    account_name: Optional[str] = None,
    event_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50), 
    offset: int = Query(0), 
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import and_
    stmt = select(ControlActionLog, ControlResource.service_type).outerjoin(
        ControlResource,
        and_(ControlActionLog.native_id == ControlResource.resource_id, ControlActionLog.account_name == ControlResource.account_name)
    )
    
    if account_name and account_name != 'All Accounts':
        stmt = stmt.where(ControlActionLog.account_name == account_name)
        
    if event_type and event_type != 'All':
        if event_type == 'power':
            stmt = stmt.where(ControlActionLog.action_type.in_(['MANUAL START', 'MANUAL STOP', 'SCHEDULE START', 'SCHEDULE STOP', 'SCHEDULED_START', 'SCHEDULED_STOP']))
        elif event_type == 'schedule':
            stmt = stmt.where(ControlActionLog.action_type == 'SCHEDULE_UPDATED')
            
    if search:
        search_term = f"%{search}%"
        stmt = stmt.where(
            (ControlActionLog.native_id.ilike(search_term)) |
            (ControlActionLog.resource_name.ilike(search_term)) |
            (ControlActionLog.action_type.ilike(search_term))
        )
        
    stmt = stmt.order_by(ControlActionLog.timestamp.desc()).limit(limit).offset(offset)
    res = await db.execute(stmt)
    rows = res.all()
    
    logs = []
    for row in rows:
        log = row[0].__dict__.copy()
        log.pop('_sa_instance_state', None)
        log['service_type'] = row[1] if row[1] else "Unknown"
        logs.append(log)
    return logs

@router.post("/log-action")
async def log_action(payload: LogActionPayload, db: AsyncSession = Depends(get_db)):
    # get provider from config
    stmt = select(ConfigCloudAccount).where(ConfigCloudAccount.account_name == payload.account_name)
    res = await db.execute(stmt)
    config = res.scalars().first()
    provider = config.provider if config else "aws"
    
    # get resource name
    sched_stmt = select(ControlResource).where(ControlResource.resource_id == payload.resource_id)
    sched_res = await db.execute(sched_stmt)
    sched = sched_res.scalars().first()
    
    log_control_action(
        session=db,
        native_id=payload.resource_id,
        account_name=payload.account_name,
        provider=provider,
        action_type=payload.action_type,
        status=payload.status,
        details=payload.details,
        resource_name=sched.resource_name if sched else payload.resource_id,
        resource_type=sched.service_type if sched else None
    )
    await db.commit()
    return {"status": "success"}

from app.core.database import SessionLocal
from app.services.sync_tracker import set_sync_status, get_sync_status
import asyncio

async def _background_control_sync(account_name: Optional[str], region: str = "all") -> str:
    configs_to_process = []
    try:
        async with SessionLocal() as db:
            print(f"[Backend Sync] Starting sync. Target account: {account_name if account_name else 'ALL'}")
            stmt = select(ConfigCloudAccount)
            if account_name:
                stmt = stmt.where(ConfigCloudAccount.account_name == account_name)
            res = await db.execute(stmt)
            configs = res.scalars().all()
            for c in configs:
                configs_to_process.append({
                    "id": c.id,
                    "account_name": c.account_name,
                    "provider": c.provider,
                    "default_region": c.default_region,
                    "encrypted_credentials": c.encrypted_credentials,
                    "verified": c.verified
                })
            
            print(f"[Backend Sync] Found {len(configs_to_process)} configuration(s) to process.")
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Failed to fetch configs: {e}"

    synced_count = 0
    try:
        for config in configs_to_process:
            if not config["verified"]:
                print(f"[Backend Sync] Skipping {config['account_name']} because it is not verified.")
                continue
            
            print(f"[Backend Sync] Processing account {config['account_name']} in region {config['default_region']}...")
            creds = decrypt_credentials(config["encrypted_credentials"])
            try:
                resources = await control_service.sync_provider_resources(
                    config["provider"], creds, region
                )
                print(f"[Backend Sync] Fetched {len(resources)} resources from {config['provider']}.")
            
                async with SessionLocal() as db:
                    # Pre-Sync Data Migration: Auto-Merge Orphaned Data
                    if resources:
                        from sqlalchemy import update
                        active_linked = resources[0].get("linked_account")
                        if active_linked:
                            # Find old accounts to migrate
                            old_accounts_stmt = select(ControlResource.account_name).where(
                                ControlResource.cloud_provider == config["provider"],
                                ControlResource.linked_account == active_linked,
                                ControlResource.account_name != config["account_name"]
                            ).distinct()
                            old_accounts = (await db.execute(old_accounts_stmt)).scalars().all()
                        
                            if old_accounts:
                                # Migrate ControlResource
                                await db.execute(
                                    update(ControlResource)
                                    .where(
                                        ControlResource.cloud_provider == config["provider"],
                                        ControlResource.linked_account == active_linked,
                                        ControlResource.account_name != config["account_name"]
                                    )
                                    .values(account_name=config["account_name"])
                                )
                                # Migrate ControlActionLog
                                await db.execute(
                                    update(ControlActionLog)
                                    .where(ControlActionLog.account_name.in_(old_accounts))
                                    .values(account_name=config["account_name"])
                                )
                                await db.commit()
                
                    # Fetch existing PARENT/Managed resources from DB to track stale ones
                    from sqlalchemy import or_
                    from app.models.control.control_resource import ServiceType
                    
                    stmt = select(ControlResource).where(
                        ControlResource.account_name == config["account_name"],
                        ControlResource.cloud_provider == config["provider"]
                    )
                    existing_schedules = (await db.execute(stmt)).scalars().all()
                    
                    if region != "all":
                        # Support comma-separated multi-region: only consider resources in those specific regions as stale
                        target_regions = {r.strip() for r in region.split(',') if r.strip()}
                        existing_ids = {s.resource_id for s in existing_schedules if s.region in target_regions}
                    else:
                        existing_ids = {s.resource_id for s in existing_schedules}
                
                    fetched_ids = set()
                    
                    CHUNK_SIZE = 1000
                    for i in range(0, len(resources), CHUNK_SIZE):
                        chunk = resources[i:i + CHUNK_SIZE]
                        try:
                            for r in chunk:
                                fetched_ids.add(r['resource_id'])
                                # Upsert into ControlResource
                                sched = await db.get(ControlResource, r['resource_id'])
                                if not sched:
                                    sched = ControlResource(
                                        resource_id=r['resource_id'],
                                        service_type=r['service_type'],
                                        control_type=r['control_type'],
                                        resource_name=r.get('resource_name', r['resource_id']),
                                        status=r.get('status', 'UNKNOWN'),
                                        instance_spec=r.get('instance_spec', 'unknown'),
                                        cloud_provider=config["provider"],
                                        account_name=config["account_name"],
                                        linked_account=r.get('linked_account'),
                                        region=r.get('region', config["default_region"]),
                                        tags_json=json.dumps(r.get('tags', {})),
                                        parent_resource_id=r.get('parent_resource_id'),
                                        is_automation_enabled=False
                                    )
                                    db.add(sched)
                                
                                    # Log the discovery
                                    log_control_action(
                                        session=db,
                                        native_id=r['resource_id'],
                                        account_name=config["account_name"],
                                        provider=config["provider"],
                                        action_type="AUTO DISCOVERY",
                                        status="SUCCESS",
                                        details="Resource auto-discovered and added",
                                        resource_name=r.get('resource_name', r['resource_id']),
                                        resource_type=r['service_type']
                                    )
                                
                                    from app.models.system.system_notification import SystemNotification
                                    notification = SystemNotification(
                                        title="New Resource Discovered",
                                        message=f"{sched.resource_name} ({sched.resource_id}) was newly discovered during sync.",
                                        type="INFO",
                                        module="CONTROL"
                                    )
                                    db.add(notification)
                                else:
                                    sched.service_type = r['service_type']
                                    sched.control_type = r['control_type']
                                    sched.resource_name = r.get('resource_name', r['resource_id'])
                                    sched.cloud_provider = config["provider"]
                                    sched.account_name = config["account_name"]
                                    sched.status = r.get('status', 'UNKNOWN')
                                    sched.instance_spec = r.get('instance_spec', 'unknown')
                                    sched.tags_json = json.dumps(r.get('tags', {}))
                                    
                                    # Scale-to-Zero Protection: If an ASG scales to 0, it may lose the EC2 instance tags
                                    # needed to map it to its parent EKS/ECS cluster. If the new sync returns None for parent,
                                    # but we already had a parent mapped, preserve the existing parent relationship.
                                    if r.get('parent_resource_id') is None and sched.parent_resource_id and sched.service_type == 'ASG':
                                        pass
                                    else:
                                        sched.parent_resource_id = r.get('parent_resource_id')
                                    
                                    sched.linked_account = r.get('linked_account')
                                    sched.region = r.get('region', config["default_region"])
                            await db.commit()
                        except Exception as e:
                            import traceback
                            traceback.print_exc()
                            print(f"[Backend Sync] Error processing chunk {i}: {e}")
                            await db.rollback()
                        
                    # Delete stale resources that no longer exist in AWS
                    stale_ids = existing_ids - fetched_ids
                    for stale_id in stale_ids:
                        sched_to_delete = await db.get(ControlResource, stale_id)
                        if sched_to_delete:
                            # 1. Cascade delete orphaned children (e.g. EC2 instances)
                            children_stmt = select(ControlResource).where(ControlResource.parent_resource_id == stale_id)
                            children = (await db.execute(children_stmt)).scalars().all()
                            for child in children:
                                await db.delete(child)
                                print(f"[Backend Sync] Deleted orphaned child resource: {child.resource_id}")
                                
                            # 2. Delete the parent
                            await db.delete(sched_to_delete)
                            print(f"[Backend Sync] Deleted stale resource: {stale_id}")
                        
                    # Garbage collect child resources that have reached TERMINATED state
                    dead_children_stmt = select(ControlResource).where(
                        ControlResource.account_name == config["account_name"],
                        ControlResource.cloud_provider == config["provider"],
                        ControlResource.parent_resource_id != None,
                        ControlResource.status == 'TERMINATED'
                    )
                    dead_children = (await db.execute(dead_children_stmt)).scalars().all()
                    for dead in dead_children:
                        await db.delete(dead)
                        print(f"[Backend Sync] Garbage collected dead child resource: {dead.resource_id}")
                        
                    synced_count += len(resources)
                    await db.commit()
                    
            except Exception as e:
                err_str = str(e)
                import traceback
                traceback.print_exc()
                print(f"[Backend Sync] Failed to sync account {config['account_name']}: {e}")
                async with SessionLocal() as db:
                    if "ExpiredToken" in err_str or "InvalidClientTokenId" in err_str or "InvalidAccessKeyId" in err_str:
                        db_config = await db.get(ConfigCloudAccount, config["id"])
                        if db_config:
                            db_config.verified = False
                            if "ExpiredToken" in err_str or ("InvalidClientTokenId" in err_str and creds.get("aws_session_token")):
                                db_config.last_error = "AWS Session Token has expired or is invalid."
                            else:
                                db_config.last_error = "Invalid AWS Access Key ID."
                                
                    from app.models.system.system_notification import SystemNotification
                    notification = SystemNotification(
                        title="Control Sync Failed",
                        message=f"Failed to sync {config['account_name']}: {err_str}",
                        type="ERROR",
                        module="CONTROL"
                    )
                    db.add(notification)
                    await db.commit()
                pass # Skip failed providers or log them
            
        async with SessionLocal() as db:
            if synced_count > 0:
                # Fetch actionable count to display alongside total to avoid confusion with dashboard counts
                from app.repositories.control_repository import control_repository
                summary = await control_repository.get_dashboard_summary(db)
                actionable_count = summary.get("total_count", 0)
                msg = f"Successfully synced {synced_count} total resources ({actionable_count} actionable)."
                from app.models.system.system_notification import SystemNotification
                notification = SystemNotification(
                    title="Control Sync Completed",
                    message=msg,
                    type="SUCCESS",
                    module="CONTROL"
                )
                db.add(notification)
                await db.commit()
                return msg
                
            return "Sync completed (no resources to sync)."
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Backend Sync] Fatal error during sync: {e}")
        return f"Fatal error: {e}"

@router.post("/sync")
async def sync_resources(account_name: Optional[str] = None, region: str = "all"):
    target_account = account_name or "ALL"
    if get_sync_status("control", target_account):
        return {"status": "already_syncing"}
        
    set_sync_status("control", target_account, True)
    
    async def task_wrapper():
        try:
            msg = await _background_control_sync(account_name, region)
            set_sync_status("control", target_account, False, msg)
        except Exception as e:
            print(f"Background sync failed: {e}")
            set_sync_status("control", target_account, False, f"Failed: {str(e)}")
            
    asyncio.create_task(task_wrapper())
    return {"status": "started"}

@router.get("/sync-status")
async def get_control_sync_status(account_name: Optional[str] = None):
    from app.services.sync_tracker import get_sync_state
    return get_sync_state("control", account_name or "ALL")

@router.get("/state/{provider}/{region}/{service_type}/{resource_id:path}")
async def get_live_state(
    provider: str,
    region: str,
    service_type: str,
    resource_id: str,
    account_name: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(ConfigCloudAccount)
    if account_name:
        stmt = stmt.where(ConfigCloudAccount.account_name == account_name)
    else:
        stmt = stmt.where(ConfigCloudAccount.is_active == True)
        
    result = await db.execute(stmt)
    config = result.scalars().first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Active cloud configuration not found")
        
    creds = decrypt_credentials(config.encrypted_credentials)
    
    state = await control_service.get_resource_state(provider, creds, region, service_type, resource_id)
    
    # Keep the database perfectly in sync with the live polled state
    sched_stmt = select(ControlResource).where(ControlResource.resource_id == resource_id)
    sched_res = await db.execute(sched_stmt)
    sched = sched_res.scalars().first()
    if sched and sched.status != state:
        # Prevent bouncing backwards due to AWS eventual consistency
        if sched.status == "STOPPING" and state in ["RUNNING", "AVAILABLE"]:
            pass # Wait for it to actually stop
        elif sched.status == "STARTING" and state in ["STOPPED", "PAUSED"]:
            pass # Wait for it to actually start
        else:
            old_status = sched.status
            sched.status = state
            
            import json
            config_data = json.loads(sched.saved_config_json) if sched.saved_config_json else {}
            
            if old_status in ["STARTING", "PENDING"] and state in ["RUNNING", "AVAILABLE"]:
                action_type = config_data.get('last_action', 'POWER_ON')
                log_control_action(
                    session=db,
                    native_id=sched.resource_id,
                    account_name=sched.account_name,
                    provider=sched.cloud_provider,
                    action_type=action_type,
                    status="SUCCESS",
                    details="Resource started successfully.",
                    resource_name=sched.resource_name,
                    resource_type=sched.service_type
                )
            elif old_status in ["STOPPING", "SHUTTING-DOWN"] and state in ["STOPPED", "PAUSED"]:
                action_type = config_data.get('last_action', 'POWER_OFF')
                log_control_action(
                    session=db,
                    native_id=sched.resource_id,
                    account_name=sched.account_name,
                    provider=sched.cloud_provider,
                    action_type=action_type,
                    status="SUCCESS",
                    details="Resource stopped successfully.",
                    resource_name=sched.resource_name,
                    resource_type=sched.service_type
                )
                
            await db.commit()
    return {"resource_id": resource_id, "status": state}

@router.get("/db-state/{resource_id:path}")
async def get_db_state(resource_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(ControlResource).where(ControlResource.resource_id == resource_id)
    res = await db.execute(stmt)
    sched = res.scalars().first()
    if not sched:
        raise HTTPException(status_code=404, detail="Resource not found")
    return {"status": sched.status}


    from sqlalchemy import text
    await db.commit()
    return {'status': 'success'}
