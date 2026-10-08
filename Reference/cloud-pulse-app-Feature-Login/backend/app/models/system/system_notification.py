from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from app.core.database import Base

class SystemNotification(Base):
    __tablename__ = 'system_notifications'

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    message = Column(String(1000), nullable=False)
    type = Column(String(50), nullable=False, default='info') # success, error, info, warning
    module = Column(String(50), nullable=False, default='system') # control, inventory, config, system
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

