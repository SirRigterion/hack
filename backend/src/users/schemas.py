from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from src.db.models import UserStatus


class UserProfile(BaseModel):
    user_id: int
    user_login: str
    user_full_name: str
    user_email: EmailStr
    avatar_url: Optional[str] = Field(default=None, alias="user_avatar_url")
    role_id: int
    registered_at: datetime
    is_deleted: bool
    status: UserStatus
    ban_reason: Optional[str]
    banned_at: Optional[datetime]

    class Config:
        from_attributes = True
        populate_by_name = True


class UserUpdate(BaseModel):
    user_login: Optional[str] = Field(default=None, min_length=3, max_length=50)
    user_full_name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    user_email: Optional[EmailStr] = Field(default=None)


class UserRestoreRequest(BaseModel):
    full_name: str
    login: str
    password: str


class UserSearchFilters(BaseModel):
    user_login: Optional[str] = None
    user_full_name: Optional[str] = None
    user_email: Optional[str] = None
    role_id: Optional[int] = None
    limit: int = Field(default=10, ge=1, le=100)