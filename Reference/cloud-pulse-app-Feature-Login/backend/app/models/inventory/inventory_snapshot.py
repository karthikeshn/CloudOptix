from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from app.core.database import Base

class InventorySnapshot(Base):
    __tablename__ = "inventory_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(DateTime, default=datetime.utcnow)
    account_name = Column(String, default="default")
    total_active_count = Column(Integer, default=0)
    billable_count = Column(Integer, default=0)
    non_billable_count = Column(Integer, default=0)
    deleted_today = Column(Integer, default=0)
    category_breakdown = Column(Text, nullable=True)
