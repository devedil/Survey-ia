from enum import StrEnum

from pydantic import BaseModel, Field


class QuestionType(StrEnum):
    FREE_TEXT = "free_text"
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    NUMERIC_SCALE = "numeric_scale"
    YES_NO = "yes_no"
    DATE = "date"
    NUMBER = "number"
    MATRIX = "matrix"
    UNKNOWN = "unknown"


class QuestionAnalyzeRequest(BaseModel):
    question_text: str = Field(..., min_length=1, max_length=4000)
    options: list[str] = Field(default_factory=list, max_length=100)
    required: bool | None = None
    max_length: int | None = Field(default=None, ge=1, le=10000)


class QuestionAnalysis(BaseModel):
    question_text: str = Field(..., min_length=1, max_length=4000)
    instructions: list[str] = Field(default_factory=list)
    question_type: QuestionType
    options: list[str] = Field(default_factory=list)
    required: bool | None = None
    max_length: int | None = Field(default=None, ge=1, le=10000)
    language: str = Field(default="unknown", max_length=50)
    requests_personal_information: bool = False
    needs_additional_context: bool = False
