from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from backend.app.questions.schemas import QuestionAnalysis


class SupportStatus(StrEnum):
    SUPPORTED = "supported"
    INSUFFICIENT = "insufficient"
    CONTRADICTORY = "contradictory"
    SENSITIVE = "sensitive"


class AnswerFormat(StrEnum):
    TEXT = "text"
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CORRECTED = "corrected"


class AnswerSource(BaseModel):
    source_type: str
    source_id: str
    excerpt: str = Field(..., min_length=1, max_length=1000)


class AnswerProposeRequest(BaseModel):
    profile_id: str
    question_text: str = Field(..., min_length=1, max_length=4000)
    options: list[str] = Field(default_factory=list, max_length=100)
    required: bool | None = None
    max_length: int | None = Field(default=None, ge=1, le=10000)


class AnswerProposal(BaseModel):
    proposal_id: str | None = None
    created_fact_id: str | None = None
    status: ProposalStatus = ProposalStatus.PENDING
    suggested_answer: str = Field(default="", max_length=10000)
    support_status: SupportStatus
    confidence: float = Field(..., ge=0.0, le=1.0)
    sources: list[AnswerSource] = Field(default_factory=list)
    needs_user_input: bool
    needs_review: bool
    review_reason: str | None = None
    answer_format: AnswerFormat = AnswerFormat.TEXT
    question_analysis: QuestionAnalysis


class AnswerProposalHistoryItem(BaseModel):
    proposal_id: str
    profile_id: str
    question_text: str
    suggested_answer: str
    support_status: SupportStatus
    confidence: float
    status: ProposalStatus
    answer_format: AnswerFormat
    created_at: datetime
    sources: list[AnswerSource]


class ApproveProposalRequest(BaseModel):
    save_as_fact: bool = False
    field_name: str | None = Field(default=None, min_length=1, max_length=150)
    category: str = Field(default="general", max_length=100)
    sensitivity: bool = False
    consent_to_retrieve: bool = False
    valid_until: datetime | None = None
    notes: str | None = None


class RejectProposalRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class CorrectProposalRequest(BaseModel):
    correction: str = Field(..., min_length=1, max_length=10000)
    save_as_fact: bool = False
    field_name: str | None = Field(default=None, min_length=1, max_length=150)
    category: str = Field(default="general", max_length=100)
    sensitivity: bool = False
    consent_to_retrieve: bool = False
    valid_until: datetime | None = None
    notes: str | None = None


class UserFeedbackRead(BaseModel):
    id: str
    proposal_id: str
    feedback_type: str
    correction: str | None
    previous_answer: str | None
    reason: str | None
    approved_for_memory: bool
    created_at: datetime

    model_config = {"from_attributes": True}
