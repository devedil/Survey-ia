from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.memory.schemas import DuplicateFact, MemoryExport, MemorySearchRequest
from backend.app.memory.service import (
    export_profile_memory,
    list_memory,
    search_memory,
)
from backend.app.profiles.models import ProfileFact
from backend.app.profiles.repository import delete_profile_fact, expire_due_profile_facts, get_profile
from backend.app.profiles.schemas import ProfileFactRead
from backend.app.validation.consistency_checker import normalize_fact_value

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("", response_model=list[ProfileFactRead])
def list_facts(
    profile_id: str,
    query: str | None = None,
    include_expired: bool = False,
    db: Session = Depends(get_db),
) -> list[ProfileFactRead]:
    if get_profile(db, profile_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    expire_due_profile_facts(db, profile_id)
    return [
        ProfileFactRead.model_validate(fact)
        for fact in list_memory(db, profile_id, query, include_expired)
    ]


@router.post("/search", response_model=list[ProfileFactRead])
def search_facts(
    payload: MemorySearchRequest,
    db: Session = Depends(get_db),
) -> list[ProfileFactRead]:
    if get_profile(db, payload.profile_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return [
        ProfileFactRead.model_validate(fact)
        for fact in search_memory(db, payload.profile_id, payload.query, payload.limit)
    ]


@router.get("/duplicates", response_model=list[DuplicateFact])
def list_duplicates(
    profile_id: str,
    db: Session = Depends(get_db),
) -> list[DuplicateFact]:
    if get_profile(db, profile_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    expire_due_profile_facts(db, profile_id)
    facts = db.scalars(
        select(ProfileFact).where(
            ProfileFact.profile_id == profile_id,
            ProfileFact.status == "verified",
            ProfileFact.is_verified.is_(True),
        )
    ).all()
    grouped_facts: dict[tuple[str, str, str], list[ProfileFact]] = {}
    for fact in facts:
        key = (
            normalize_fact_value(fact.category),
            normalize_fact_value(fact.field_name),
            normalize_fact_value(fact.value),
        )
        grouped_facts.setdefault(key, []).append(fact)
    return [
        DuplicateFact(
            field_name=matches[0].field_name,
            category=matches[0].category,
            fact_ids=[match.id for match in matches],
            value=matches[0].value,
        )
        for matches in grouped_facts.values()
        if len(matches) > 1
    ]


@router.get("/export", response_model=MemoryExport)
def export_memory(profile_id: str, db: Session = Depends(get_db)) -> MemoryExport:
    if get_profile(db, profile_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return MemoryExport.model_validate(export_profile_memory(db, profile_id))


@router.delete("/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory_fact(
    fact_id: str,
    profile_id: str,
    db: Session = Depends(get_db),
) -> Response:
    if get_profile(db, profile_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    fact = db.scalar(
        select(ProfileFact).where(
            ProfileFact.id == fact_id,
            ProfileFact.profile_id == profile_id,
        )
    )
    if fact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory fact not found")
    delete_profile_fact(db, fact)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_memory(profile_id: str, db: Session = Depends(get_db)) -> Response:
    if get_profile(db, profile_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    facts = db.scalars(select(ProfileFact).where(ProfileFact.profile_id == profile_id)).all()
    for fact in facts:
        db.delete(fact)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
