from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class SystemNotificationResponse(BaseModel):
    id: int
    title: str
    message: str
    type: str
    module: str
    is_read: bool
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

