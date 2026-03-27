from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime
from typing import Optional
from uuid import UUID
from ..db.models import Tier


class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

    @field_validator("username")
    @classmethod
    def username_length(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Username must be at least 2 characters")
        if len(v) > 50:
            raise ValueError("Username must be 50 characters or fewer")
        return v


class LogIn(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    uid: UUID
    username: str
    role: str


class UserOut(BaseModel):
    id: UUID
    username: str
    email: str
    tier: Tier
    is_active: bool
    tg_chat_id: Optional[str] = None
    subscription_expires: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True, "json_encoders": {datetime: lambda v: v.isoformat(), UUID: str}}


class TelegramLinkRequest(BaseModel):
    tg_chat_id: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v