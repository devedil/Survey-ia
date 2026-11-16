from datetime import datetime
from typing import Literal

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
    source_type: str = Field(default="user", max_length=50)
    source_id: str | None = Field(default=None, max_length=36)
    category: str = Field(default="general", max_length=100)
    status: Literal["pending", "verified", "rejected", "expired"] = "verified"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    is_verified: bool = True
    sensitivity: bool = False
    consent_to_retrieve: bool = True
    confirmed_at: datetime | None = None
    valid_until: datetime | None = None
    notes: str | None = None


class ProfileFactCreate(ProfileFactBase):
    status: Literal["pending", "verified", "rejected", "expired"] | None = None


class ProfileFactUpdate(BaseModel):
    field_name: str | None = Field(default=None, min_length=1, max_length=150)
    value: str | None = Field(default=None, min_length=1)
    source: str | None = Field(default=None, max_length=100)
    source_type: str | None = Field(default=None, max_length=50)
    source_id: str | None = Field(default=None, max_length=36)
    category: str | None = Field(default=None, max_length=100)
    status: Literal["pending", "verified", "rejected", "expired"] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_verified: bool | None = None
    sensitivity: bool | None = None
    consent_to_retrieve: bool | None = None
    confirmed_at: datetime | None = None
    valid_until: datetime | None = None
    notes: str | None = None


class ProfileFactRead(ProfileFactBase):
    id: str
    profile_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProfileFactRevisionRead(BaseModel):
    id: str
    fact_id: str
    change_type: str
    before: dict | None
    after: dict
    created_at: datetime

    model_config = {"from_attributes": True}
