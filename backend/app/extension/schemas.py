from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from backend.app.answers.schemas import AnswerProposeRequest


class ExtensionProfileRead(BaseModel):
    id: str
    name: str


class ExtensionProposeRequest(AnswerProposeRequest):
    origin: str = Field(..., min_length=1, max_length=512)


class ExtensionProposalAction(BaseModel):
    profile_id: str
    origin: str = Field(..., min_length=1, max_length=512)


class ExtensionCorrectionRequest(ExtensionProposalAction):
    correction: str = Field(..., min_length=1, max_length=10000)


class ExtensionRejectRequest(ExtensionProposalAction):
    reason: str | None = Field(default=None, max_length=2000)


class ExtensionAuditCreate(BaseModel):
    profile_id: str
    origin: str = Field(..., min_length=1, max_length=512)
    action: Literal[
        "question_inspected",
        "field_filled",
        "policy_blocked",
    ]
    control_type: str | None = Field(default=None, max_length=40)


class ExtensionAuditRead(BaseModel):
    id: str
    profile_id: str
    origin: str
    action: str
    control_type: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
