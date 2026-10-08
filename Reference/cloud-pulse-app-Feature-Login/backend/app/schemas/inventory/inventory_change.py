from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class InventoryChangeBase(BaseModel):
    native_id: str
    account_name: str
    change_type: str
    details: Optional[str] = None

class InventoryChangeResponse(InventoryChangeBase):
    id: int
    timestamp: datetime
    
    class Config:
        from_attributes = True
