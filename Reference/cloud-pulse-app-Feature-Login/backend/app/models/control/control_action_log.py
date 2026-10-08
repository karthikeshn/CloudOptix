from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from app.core.database import Base

class ControlActionLog(Base):
    __tablename__ = "control_action_logs"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    native_id = Column(String, index=True, nullable=False)
    resource_name = Column(String, nullable=True)
    account_name = Column(String, nullable=False)
    linked_account = Column(String, nullable=True, index=True)
    provider = Column(String, nullable=False)
    resource_type = Column(String, nullable=True)
    action_type = Column(String, nullable=False) # e.g. 'MANUAL_START', 'SCHEDULED_STOP', 'SCHEDULE_UPDATED'
    status = Column(String, nullable=False) # 'SUCCESS', 'FAILED'
    details = Column(String, nullable=True)
