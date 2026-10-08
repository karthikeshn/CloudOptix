from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from app.core.database import Base

class InventoryChange(Base):
    __tablename__ = "inventory_changes"
    id = Column(Integer, primary_key=True, index=True)
    native_id = Column(String, index=True, nullable=False)
    account_name = Column(String, default="default")
    change_type = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
