from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.models.control.control_resource import ServiceType, ControlType

class ControlResourceBase(BaseModel):
    resource_id: str
    resource_name: Optional[str] = None
    cloud_provider: str = "aws"
    account_name: str = "default"
    region: str
    service_type: ServiceType
    control_type: ControlType
    status: str
    instance_spec: Optional[str] = None
    saved_config_json: Optional[str] = None
    tags_json: Optional[str] = None
    parent_resource_id: Optional[str] = None
    
    is_automation_enabled: bool
    disabled_dates: Optional[list[str]] = []
    start_time: str = "10:00"
    stop_time: str = "21:00"
    timezone: str = "Asia/Kolkata"

class ControlResourceCreate(ControlResourceBase):
    pass

class ControlResourceResponse(ControlResourceBase):
    last_synced_at: datetime
    
    class Config:
        from_attributes = True

class ScheduleUpdatePayload(BaseModel):
    resource_id: str
    service_type: str
    account_name: str
    region: str = "us-east-1"
    is_automation_enabled: bool
    disabled_dates: Optional[list[str]] = []
    start_time: str = "10:00"
    stop_time: str = "21:00"
    timezone: str = "Asia/Kolkata"

class ManualPowerActionPayload(BaseModel):
    resource_id: str
    service_type: str
    account_name: str
    region: str = "us-east-1"
    action: str  # 'START' | 'STOP'
