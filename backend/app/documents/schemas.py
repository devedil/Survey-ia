from datetime import datetime

from pydantic import BaseModel, Field


class DocumentRead(BaseModel):
    id: str
    profile_id: str
    filename: str
    mime_type: str
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    chunk_count: int = 0

    model_config = {"from_attributes": True}


class DocumentSearchRequest(BaseModel):
    profile_id: str
    query: str = Field(..., min_length=1, max_length=4000)
    limit: int = Field(default=5, ge=1, le=20)


class DocumentSearchResult(BaseModel):
    document_id: str
    filename: str
    chunk_id: str
    chunk_index: int
    content: str
    score: float
    metadata: dict
