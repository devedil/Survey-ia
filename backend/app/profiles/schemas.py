from datetime import datetime

from pydantic import BaseModel, Field


class ProfileBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)


class ProfileCreate(ProfileBase):
    pass


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)


class ProfileRead(ProfileBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProfileFactBase(BaseModel):
    field_name: str = Field(..., min_length=1, max_length=150)
    value: str = Field(..., min_length=1)
    source: str = Field(default="user", max_length=100)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    is_verified: bool = True
    notes: str | None = None


class ProfileFactCreate(ProfileFactBase):
    pass


class ProfileFactUpdate(BaseModel):
    field_name: str | None = Field(default=None, min_length=1, max_length=150)
    value: str | None = Field(default=None, min_length=1)
    source: str | None = Field(default=None, max_length=100)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_verified: bool | None = None
    notes: str | None = None


class ProfileFactRead(ProfileFactBase):
    id: str
    profile_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
