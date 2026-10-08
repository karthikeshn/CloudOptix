from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class InventorySnapshotBase(BaseModel):
    account_name: str
    total_active_count: int = 0
    billable_count: int = 0
    non_billable_count: int = 0
    deleted_today: int = 0
    category_breakdown: Optional[str] = None

class InventorySnapshotResponse(InventorySnapshotBase):
    id: int
    snapshot_date: datetime
    
    class Config:
        from_attributes = True
