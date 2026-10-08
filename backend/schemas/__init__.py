from pydantic import BaseModel

class UserBase(BaseModel):
    username: str
    email: str | None = None
    role: str = "engineer"

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: str | None = None
    role: str | None = None
    is_active: bool | None = None

class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str

class PasswordVerifyRequest(BaseModel):
    password: str

class User(UserBase):
    id: int
    is_active: bool

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: str | None = None
    role: str | None = None

class CloudConfigBase(BaseModel):
    provider: str = "AWS"
    account_name: str | None = None
    region: str = "us-east-1"
    use_iam_role: bool = False
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    assume_role_arn: str | None = None
    external_id: str | None = None

class CloudConfigCreate(CloudConfigBase):
    pass

class CloudConfigResponse(CloudConfigBase):
    id: int
    owner_id: int
    aws_account_id: str | None = None
    last_verified: str | None = None
    status: str | None = None
    is_deleted: bool = False

    class Config:
        from_attributes = True

class TicketUpdate(BaseModel):
    status: str # Pending, Approved, Rejected, Completed
    approvalComments: str | None = None
    reasonForRejection: str | None = None

class TicketAssign(BaseModel):
    engineer_id: int

class TicketDetailsUpdate(BaseModel):
    details: str

class TicketSyncEdit(BaseModel):
    script_name: str
    resource_id: str
    field: str
    value: str

class TicketResponse(BaseModel):
    id: int
    script_name: str
    account_id: int | None
    aws_account_id: str | None = None
    resource_id: str
    potential_savings: str | None
    status: str
    details: str
    created_at: str
    recommended_action: str | None = None
    assigned_to: int | None
    assigned_to_name: str | None = None
    assigned_by_name: str | None = None
    assigned_at: str | None = None
    completed_by_name: str | None = None
    completed_at: str | None = None
    
    class Config:
        from_attributes = True
