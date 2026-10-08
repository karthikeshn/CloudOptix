from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, delete
from datetime import datetime, timedelta
from app.core.database import get_db
from app.models import ConfigCloudAccount, InventoryResource, InventoryChange, InventorySnapshot
from app.services.aws.service import AWSService
from app.services.inventory_service import sync_inventory
import json

router = APIRouter(prefix="/inventory", tags=["Inventory"])

from app.core.database import SessionLocal
from app.services.sync_tracker import set_sync_status, get_sync_status
import asyncio

async def _background_inventory_sync(provider: str, config_id: int):
    # First get the account name to set status
    account_name = "UNKNOWN"
    try:
        async with SessionLocal() as db:
            db_config = await db.get(ConfigCloudAccount, config_id)
            if not db_config:
                return
            account_name = db_config.account_name
            from app.core.security import decrypt_credentials
            creds = decrypt_credentials(db_config.encrypted_credentials)
            default_region = db_config.default_region
    except Exception as e:
        print(f"Background inventory sync failed to fetch config: {e}")
        return f"Failed: {str(e)}"
        
    set_sync_status("inventory", account_name, True)
    
    try:
        if provider == "aws":
            aws_service = AWSService()
            is_valid, msg = await aws_service.test_connection(creds)
            if not is_valid:
                raise Exception(f"AWS Authentication failed: {msg}")
            fetched_resources = await aws_service.fetch_all_resources(creds, default_region)
        elif provider == "azure":
            from app.services.azure.service import AzureService
            azure_service = AzureService()
            is_valid, msg = await azure_service.test_connection(creds)
            if not is_valid:
                raise Exception(f"Azure Authentication failed: {msg}")
            sub_id = creds.get('subscription_id')
            fetched_resources = await azure_service.fetch_all_resources(creds, sub_id)
        elif provider == "gcp":
            from app.services.gcp.service import GCPService
            gcp_service = GCPService()
            is_valid, msg = await gcp_service.test_connection(creds)
            if not is_valid:
                raise Exception(f"GCP Authentication failed: {msg}")
            fetched_resources = await gcp_service.fetch_all_resources(creds)
        else:
            raise Exception("Unsupported cloud provider")
        
        async with SessionLocal() as db:
            metrics = await sync_inventory(db, provider, account_name, fetched_resources)
            
            from app.models.system.system_notification import SystemNotification
            msg = f"Synced {metrics['total_active']} resources • {metrics['created']} new • {metrics['deleted']} deleted"
            notification = SystemNotification(
                title="Inventory Sync Completed",
                message=msg,
                type="SUCCESS",
                module="INVENTORY"
            )
            db.add(notification)
            await db.commit()
            return msg
    except Exception as e:
        err_str = str(e)
        import traceback
        traceback.print_exc()
        print(f"Background inventory sync failed: {err_str}")
        
        async with SessionLocal() as db:
            if "Authentication failed" in err_str:
                db_config = await db.get(ConfigCloudAccount, config_id)
                if db_config:
                    db_config.verified = False
                    
                    parts = err_str.split(":", 1)
                    if len(parts) > 1:
                        db_config.last_error = parts[1].strip()
                    else:
                        db_config.last_error = err_str
                    
                    from app.models.system.system_notification import SystemNotification
                    notification = SystemNotification(
                        title="Inventory Sync Failed",
                        message=f"Authentication failed for {account_name}: {db_config.last_error}",
                        type="ERROR",
                        module="INVENTORY"
                    )
                    db.add(notification)
                    await db.commit()
            else:
                from app.models.system.system_notification import SystemNotification
                notification = SystemNotification(
                    title="Inventory Sync Failed",
                    message=f"Failed to sync {account_name}: {err_str}",
                    type="ERROR",
                    module="INVENTORY"
                )
                db.add(notification)
                await db.commit()
                
        return f"Failed: {err_str}"

@router.post("/sync")
async def trigger_sync(
    provider: str = Query(...), 
    config_id: int = Query(...),
    db: AsyncSession = Depends(get_db)
):
    # Need to quickly get account_name to check if it's already syncing
    db_config = await db.get(ConfigCloudAccount, config_id)
    if not db_config:
        raise HTTPException(status_code=404, detail="Config not found")
        
    if get_sync_status("inventory", db_config.account_name):
        return {"status": "already_syncing"}
        
    set_sync_status("inventory", db_config.account_name, True)
        
    async def task_wrapper():
        msg = await _background_inventory_sync(provider, config_id)
        if db_config.account_name:
            set_sync_status("inventory", db_config.account_name, False, msg)

    asyncio.create_task(task_wrapper())
    return {"status": "started"}

@router.get("/sync-status")
async def get_inventory_sync_status(account_name: str = Query(...)):
    from app.services.sync_tracker import get_sync_state
    return get_sync_state("inventory", account_name)

@router.get("/summary")
async def get_summary(account: str = Query(None), db: AsyncSession = Depends(get_db)):
    from app.repositories.inventory_repository import inventory_repository
    return await inventory_repository.get_summary(db, account)

@router.delete("/wipe")
async def wipe_database(provider: str = Query(None), account: str = Query(None), db: AsyncSession = Depends(get_db)):
    from app.repositories.inventory_repository import inventory_repository
    await inventory_repository.wipe_database(db, provider, account)
    return {"status": "wiped"}

@router.get("/changes")
async def get_changes(
    account: str = Query(None), 
    days: int = Query(30), 
    change_type: str = Query(None),
    search: str = Query(None),
    region: str = Query(None),
    linked_account: str = Query(None),
    tag: str = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db)
):
    from app.repositories.inventory_repository import inventory_repository
    return await inventory_repository.get_changes(
        db, account, days, change_type, search, region, linked_account, tag, limit, offset
    )

@router.get("/trend")
async def get_trend(account: str = Query(None), resource_type: str = Query(None), days: int = Query(30), db: AsyncSession = Depends(get_db)):
    from app.repositories.inventory_repository import inventory_repository
    return await inventory_repository.get_trend(db, account, resource_type, days)

@router.get("/summary/advanced")
async def get_advanced_summary(
    account: str = Query(None), 
    provider: str = Query(None), 
    region: str = Query(None),
    linked_account: str = Query(None),
    tag: str = Query(None),
    resource_type: str = Query(None),
    db: AsyncSession = Depends(get_db)
):
    from app.repositories.inventory_repository import inventory_repository
    return await inventory_repository.get_advanced_summary(db, account, provider, region, linked_account, tag, resource_type)

@router.get("/resources")
async def get_resources(
    account: str = Query(None),
    provider: str = Query(None),
    resource_type: str = Query(None),
    region: str = Query(None),
    billable: bool = Query(None),
    linked_account: str = Query(None),
    tag: str = Query(None),
    time_filter: str = Query(None),
    status: str = Query("active"),
    limit: int = Query(50),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db)
):
    from app.repositories.inventory_repository import inventory_repository
    return await inventory_repository.get_paginated_resources(
        db=db, account=account, provider=provider, resource_type=resource_type, 
        region=region, billable=billable, linked_account=linked_account, tag=tag,
        time_filter=time_filter, status=status, limit=limit, offset=offset
    )

@router.get("/filter-options")
async def get_filter_options(account: str = Query(None), provider: str = Query(None), db: AsyncSession = Depends(get_db)):
    from app.repositories.inventory_repository import inventory_repository
    return await inventory_repository.get_filter_options(db, account, provider)

@router.get("/activity-heatmap")
async def get_activity_heatmap(account: str = Query(None), resource_type: str = Query(None), db: AsyncSession = Depends(get_db)):
    from app.repositories.inventory_repository import inventory_repository
    return await inventory_repository.get_activity_heatmap(db, account, resource_type)
