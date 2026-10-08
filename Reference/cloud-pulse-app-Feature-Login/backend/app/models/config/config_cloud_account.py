from sqlalchemy import Column, Integer, String, Boolean
from app.core.database import Base

class ConfigCloudAccount(Base):
    __tablename__ = "config_cloud_accounts"
    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, nullable=False)
    account_name = Column(String, unique=True, index=True, nullable=False)
    default_region = Column(String, default="us-east-1")
    encrypted_credentials = Column(String, nullable=False)
    verified = Column(Boolean, default=False)
    auto_sync_enabled = Column(Boolean, default=False)
    auto_sync_time = Column(String, default="10:00")
    auto_sync_timezone = Column(String, default="Asia/Kolkata")
    last_sync_date = Column(String, nullable=True)
    active_modules = Column(String, default="inventory,control")
    last_error = Column(String, nullable=True)
