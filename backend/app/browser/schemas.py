from datetime import datetime

from pydantic import BaseModel, Field


class BrowserSessionCreate(BaseModel):
    profile_id: str


class BrowserSessionRead(BaseModel):
    session_id: str
    profile_id: str
    status: str
    current_url: str | None
    created_at: datetime


class BrowserNavigateRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)


class BrowserControlRead(BaseModel):
    control_id: str
    question_text: str
    control_type: str
    options: list[str] = Field(default_factory=list)
    required: bool
    max_length: int | None = None


class BrowserInspectionRead(BaseModel):
    url: str
    title: str
    controls: list[BrowserControlRead]


class BrowserProposeRequest(BaseModel):
    control_id: str


class BrowserFillRequest(BaseModel):
    control_id: str
    proposal_id: str


class BrowserFillRead(BaseModel):
    session_id: str
    control_id: str
    proposal_id: str
    verified: bool
    status: str


class BrowserAuditEventRead(BaseModel):
    id: str
    session_id: str
    profile_id: str
    action: str
    domain: str | None
    details: dict
    created_at: datetime

    model_config = {"from_attributes": True}
