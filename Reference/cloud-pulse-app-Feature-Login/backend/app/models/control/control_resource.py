from datetime import datetime
import enum
from sqlalchemy import Column, String, DateTime, Enum, Text, Boolean
from app.core.database import Base

class ServiceType(str, enum.Enum):
    EC2 = "EC2"
    RDS = "RDS"
    AURORA = "AURORA"
    DOCUMENTDB = "DOCUMENTDB"
    REDSHIFT = "REDSHIFT"
    SAGEMAKER = "SAGEMAKER"
    WORKSPACES = "WORKSPACES"
    ASG = "ASG"
    ECS = "ECS"
    EKS = "EKS"
    APP_RUNNER = "APP_RUNNER"
    BEANSTALK = "BEANSTALK"

class ControlType(str, enum.Enum):
    DIRECT_POWER = "DIRECT_POWER"
    SCALE_TO_ZERO = "SCALE_TO_ZERO"
    DESTROY_RECREATE = "DESTROY_RECREATE"

class ControlResource(Base):
    __tablename__ = "control_resources"
    
    resource_id = Column(String, primary_key=True, index=True)
    resource_name = Column(String, nullable=True)
    cloud_provider = Column(String, default="aws", index=True)
    account_name = Column(String, nullable=False, default="default", index=True)
    linked_account = Column(String, nullable=True, index=True)
    region = Column(String, nullable=False, index=True)
    
    service_type = Column(Enum(ServiceType), nullable=False)
    control_type = Column(Enum(ControlType), nullable=False)
    status = Column(String, default="UNKNOWN")
    
    instance_spec = Column(String, nullable=True)
    saved_config_json = Column(Text, nullable=True) 
    
    # Advanced metadata
    tags_json = Column(Text, nullable=True)
    parent_resource_id = Column(String, nullable=True)
    is_visible = Column(Boolean, default=True)
    
    # Scheduling fields
    is_automation_enabled = Column(Boolean, default=False)
    disabled_dates = Column(Text, nullable=True) # JSON array of disabled dates
    start_time = Column(String, default="10:00")
    stop_time = Column(String, default="21:00")
    timezone = Column(String, default="Asia/Kolkata")
    override_state = Column(String, default="NORMAL")
    
    last_synced_at = Column(DateTime, default=datetime.utcnow)
