from sqlalchemy import Column, Integer, String, Boolean
from app.core.database import Base

class InventoryResource(Base):
    __tablename__ = "inventory_resources"
    id = Column(Integer, primary_key=True, index=True)
    native_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    resource_type = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False, index=True)
    account_name = Column(String, default="default", index=True)
    region = Column(String, nullable=False, index=True)
    linked_account = Column(String, nullable=True, index=True)
    billable = Column(Boolean, default=True)
    billing_tier = Column(String, nullable=True)
    status = Column(String, nullable=False, index=True)
    tags = Column(String, nullable=True)
    first_seen_date = Column(String, nullable=True)
    deleted_at = Column(String, nullable=True)
