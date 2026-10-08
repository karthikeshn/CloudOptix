from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.core.database import get_db
from app.models import ConfigCloudAccount
from sqlalchemy.future import select
from app.core.security import encrypt_credentials, decrypt_credentials
from app.services.aws.service import AWSService

router = APIRouter(prefix="/cloud-config", tags=["Credentials"])

class ConfigCloudAccountCreate(BaseModel):
    provider: str
    account_name: str
    default_region: str = "global"
    credentials: dict
    active_modules: str = "inventory,control"

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_config(payload: ConfigCloudAccountCreate, db: AsyncSession = Depends(get_db)):
    encrypted_str = encrypt_credentials(payload.credentials)
    
    db_config = ConfigCloudAccount(
        provider=payload.provider,
        account_name=payload.account_name,
        default_region=payload.default_region,
        encrypted_credentials=encrypted_str,
        verified=False,
        active_modules=payload.active_modules
    )
    db.add(db_config)
    await db.commit()
    await db.refresh(db_config)
    return {"id": db_config.id, "status": "stored", "verified": False}

@router.get("/")
async def list_configs(db: AsyncSession = Depends(get_db)):
    stmt = select(ConfigCloudAccount).order_by(ConfigCloudAccount.id.desc())
    result = await db.execute(stmt)
    configs = result.scalars().all()
    
    return [
        {
            "id": c.id,
            "provider": c.provider,
            "account_name": c.account_name,
            "region": c.default_region,
            "verified": c.verified,
            "auto_sync_enabled": c.auto_sync_enabled,
            "auto_sync_time": c.auto_sync_time,
            "auto_sync_timezone": c.auto_sync_timezone,
            "active_modules": getattr(c, "active_modules", "inventory,control"),
            "last_error": getattr(c, "last_error", None)
        }
        for c in configs
    ]

from sqlalchemy import delete
from app.core.database import get_db
from app.models import ConfigCloudAccount, InventoryResource, InventoryChange, InventorySnapshot

@router.delete("/{config_id}")
async def delete_config(config_id: int, db: AsyncSession = Depends(get_db)):
    db_config = await db.get(ConfigCloudAccount, config_id)
    if not db_config:
        raise HTTPException(status_code=404, detail="Configuration target not found")
        
    provider = db_config.provider
    await db.delete(db_config)
    
    # We no longer wipe the associated inventory and dashboard data so it doesn't get destroyed.
    # It remains in the database as orphaned data (or ready to be reclaimed if the config is recreated).
    
    await db.commit()
    return {"status": "success", "message": "Deleted config (dashboard data retained)"}


class ConfigCloudAccountUpdate(BaseModel):
    account_name: str | None = None
    default_region: str | None = None
    active_modules: str | None = None

@router.patch("/{config_id}")
async def update_config(config_id: int, payload: ConfigCloudAccountUpdate, db: AsyncSession = Depends(get_db)):
    db_config = await db.get(ConfigCloudAccount, config_id)
    if not db_config:
        raise HTTPException(status_code=404, detail="Configuration target not found")
        
    if payload.account_name is not None:
        db_config.account_name = payload.account_name
    if payload.default_region is not None:
        db_config.default_region = payload.default_region
    if payload.active_modules is not None:
        db_config.active_modules = payload.active_modules
        
    await db.commit()
    return {"status": "success", "message": "Config updated successfully"}


@router.post("/{config_id}/verify")
async def verify_config(config_id: int, db: AsyncSession = Depends(get_db)):
    db_config = await db.get(ConfigCloudAccount, config_id)
    if not db_config:
        raise HTTPException(status_code=404, detail="Configuration target not found")
        
    plain_creds = decrypt_credentials(db_config.encrypted_credentials)
    
    if db_config.provider == "aws":
        checker = AWSService()
        is_valid, error_msg = await checker.test_connection(plain_creds)
    elif db_config.provider == "azure":
        from app.services.azure.service import AzureService
        checker = AzureService()
        is_valid, error_msg = await checker.test_connection(plain_creds)
    elif db_config.provider == "gcp":
        from app.services.gcp.service import GCPService
        checker = GCPService()
        is_valid, error_msg = await checker.test_connection(plain_creds)
    else:
        raise HTTPException(status_code=400, detail="Unsupported cloud provider")
        
    if is_valid:
        db_config.verified = True
        db_config.last_error = None
        await db.commit()
        return {"status": "success", "message": "Connection verified successfully"}
        
    db_config.verified = False
    db_config.last_error = error_msg
    await db.commit()
    raise HTTPException(status_code=400, detail=f"Cloud verification check failed: {error_msg}")

class AutoSyncUpdate(BaseModel):
    enabled: bool
    time: str
    timezone: str

@router.patch("/{config_id}/auto-sync")
async def update_auto_sync(config_id: int, payload: AutoSyncUpdate, db: AsyncSession = Depends(get_db)):
    db_config = await db.get(ConfigCloudAccount, config_id)
    if not db_config:
        raise HTTPException(status_code=404, detail="Configuration target not found")
        
    # If the time is changed, clear last_sync_date so it can run again today at the new time
    if db_config.auto_sync_time != payload.time:
        db_config.last_sync_date = None
        
    db_config.auto_sync_enabled = payload.enabled
    db_config.auto_sync_time = payload.time
    db_config.auto_sync_timezone = payload.timezone
    await db.commit()
    
    return {"status": "success", "message": "Auto sync settings updated"}


class CredentialsUpdate(BaseModel):
    credentials: dict

@router.patch("/{config_id}/credentials")
async def update_credentials(config_id: int, payload: CredentialsUpdate, db: AsyncSession = Depends(get_db)):
    db_config = await db.get(ConfigCloudAccount, config_id)
    if not db_config:
        raise HTTPException(status_code=404, detail="Configuration target not found")
        
    existing_creds = decrypt_credentials(db_config.encrypted_credentials)
    
    # Filter out empty values so we only merge provided updates
    updates = {k: v for k, v in payload.credentials.items() if v}
    existing_creds.update(updates)
    
    db_config.encrypted_credentials = encrypt_credentials(existing_creds)
    db_config.verified = False
    db_config.last_error = None
    
    await db.commit()
    return {"status": "success", "message": "Credentials updated successfully"}
