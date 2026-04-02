from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional


class UserModel(BaseModel):
    name: str
    age: int
    phone: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        populate_by_name = True
