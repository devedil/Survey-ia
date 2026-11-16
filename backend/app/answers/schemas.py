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
    suggested_answer: str = Field(default="", max_length=10000)
    support_status: SupportStatus
    confidence: float = Field(..., ge=0.0, le=1.0)
    sources: list[AnswerSource] = Field(default_factory=list)
    needs_user_input: bool
    needs_review: bool
    review_reason: str | None = None
    answer_format: AnswerFormat = AnswerFormat.TEXT
    question_analysis: QuestionAnalysis
