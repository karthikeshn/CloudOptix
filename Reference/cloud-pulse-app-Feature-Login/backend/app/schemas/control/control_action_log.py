from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ControlActionLogBase(BaseModel):
    native_id: str
    resource_name: Optional[str] = None
    resource_type: Optional[str] = None
    account_name: str
    provider: str
    action_type: str
    status: str
    details: Optional[str] = None

class ControlActionLogCreate(ControlActionLogBase):
    pass

class ControlActionLogResponse(ControlActionLogBase):
    id: int
    timestamp: datetime
    
    class Config:
        from_attributes = True

class LogActionPayload(BaseModel):
    resource_id: str
    service_type: str
    account_name: str
    region: str
    action_type: str
    status: str
    details: str
