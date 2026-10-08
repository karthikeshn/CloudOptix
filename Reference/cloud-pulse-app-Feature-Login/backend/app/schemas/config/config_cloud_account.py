from pydantic import BaseModel
from typing import Optional

class ConfigCloudAccountBase(BaseModel):
    provider: str
    account_name: str
    default_region: str = "us-east-1"
    auto_sync_enabled: bool = False
    auto_sync_time: str = "10:00"
    auto_sync_timezone: str = "Asia/Kolkata"
    active_modules: str = "inventory,control"

class ConfigCloudAccountCreate(ConfigCloudAccountBase):
    encrypted_credentials: str

class ConfigCloudAccountResponse(ConfigCloudAccountBase):
    id: int
    verified: bool
    last_sync_date: Optional[str] = None
    
    class Config:
        from_attributes = True
