from pydantic import BaseModel, Field

from backend.app.profiles.schemas import ProfileFactRead


class MemorySearchRequest(BaseModel):
    profile_id: str
    query: str = Field(..., min_length=1, max_length=1000)
    limit: int = Field(default=20, ge=1, le=100)


class DuplicateFact(BaseModel):
    field_name: str
    category: str
    fact_ids: list[str]
    value: str


class MemoryExport(BaseModel):
    profile: dict
    facts: list[dict]
    fact_revisions: list[dict]
    proposals: list[dict]
    feedback: list[dict]
