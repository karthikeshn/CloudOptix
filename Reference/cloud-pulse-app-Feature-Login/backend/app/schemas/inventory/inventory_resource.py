from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

# --- Resource Inventory ---
class InventoryResourceBase(BaseModel):
    native_id: str
    name: Optional[str] = None
    resource_type: str
    provider: str
    account_name: str
    region: str
    linked_account: Optional[str] = None
    billable: bool = True
    billing_tier: Optional[str] = None
    status: str
    tags: Optional[str] = None
    first_seen_date: Optional[str] = None
    deleted_at: Optional[str] = None

class InventoryResourceCreate(InventoryResourceBase):
    pass

class InventoryResourceResponse(InventoryResourceBase):
    id: int
    
    class Config:
        from_attributes = True


