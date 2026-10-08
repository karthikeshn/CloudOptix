from sqlalchemy import Boolean, Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String)
    role = Column(String, default="engineer")
    is_active = Column(Boolean, default=True)

    cloud_configs = relationship("CloudConfig", back_populates="owner")

class CloudConfig(Base):
    __tablename__ = "cloud_configs"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, default="AWS")
    account_name = Column(String, nullable=True)
    region = Column(String, default="us-east-1")
    use_iam_role = Column(Boolean, default=False)
    aws_access_key_id = Column(String, nullable=True)
    aws_secret_access_key = Column(String, nullable=True)
    aws_session_token = Column(String, nullable=True)
    assume_role_arn = Column(String, nullable=True)
    external_id = Column(String, nullable=True)
    aws_account_id = Column(String, nullable=True) # Real 12-digit AWS account ID
    last_verified = Column(String, nullable=True) # ISO format timestamp
    status = Column(String, default="unverified") # 'verified', 'expired', 'invalid', 'unverified'
    is_deleted = Column(Boolean, default=False)
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="cloud_configs")

class ScriptValidation(Base):
    __tablename__ = "script_validations"

    id = Column(Integer, primary_key=True, index=True)
    script_name = Column(String, unique=True, index=True)
    status = Column(String) # 'approved', 'rejected', or None
    reason = Column(String, nullable=True)
    last_validated = Column(String) # ISO format timestamp

class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    script_name = Column(String, index=True)
    account_id = Column(Integer, ForeignKey("cloud_configs.id"), nullable=True)
    resource_id = Column(String, index=True)
    potential_savings = Column(String, nullable=True) # e.g. "15.00"
    status = Column(String, default="Pending") # Pending, Approved, Rejected, Completed
    details = Column(String) # JSON string of all other csv columns
    created_at = Column(String) # ISO format timestamp
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    recommended_action = Column(String, nullable=True)
    
    # Audit Fields
    assigned_to_name = Column(String, nullable=True)
    assigned_by_name = Column(String, nullable=True)
    assigned_at = Column(String, nullable=True)
    completed_by_name = Column(String, nullable=True)
    completed_at = Column(String, nullable=True)

    account = relationship("CloudConfig")
    assignee = relationship("User")

    @property
    def aws_account_id(self):
        return self.account.aws_account_id if self.account else None
