from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.profiles.schemas import (
    ProfileCreate,
    ProfileFactCreate,
    ProfileFactRead,
    ProfileFactUpdate,
    ProfileRead,
    ProfileUpdate,
)
from backend.app.profiles.service import profile_service

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=list[ProfileRead])
def list_profiles(db: Session = Depends(get_db)) -> list[ProfileRead]:
    profiles = profile_service.list_profiles(db)
    return [ProfileRead.model_validate(profile) for profile in profiles]


@router.post("", response_model=ProfileRead, status_code=status.HTTP_201_CREATED)
def create_profile(profile: ProfileCreate, db: Session = Depends(get_db)) -> ProfileRead:
    saved = profile_service.create_profile(db, profile.name, profile.email)
    return ProfileRead.model_validate(saved)


@router.get("/{profile_id}", response_model=ProfileRead)
def get_profile(profile_id: str, db: Session = Depends(get_db)) -> ProfileRead:
    profile = profile_service.get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return ProfileRead.model_validate(profile)


@router.patch("/{profile_id}", response_model=ProfileRead)
def update_profile(
    profile_id: str,
    updates: ProfileUpdate,
    db: Session = Depends(get_db),
) -> ProfileRead:
    profile = profile_service.get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    payload = updates.model_dump(exclude_unset=True)
    updated = profile_service.update_profile(db, profile, payload)
    return ProfileRead.model_validate(updated)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(profile_id: str, db: Session = Depends(get_db)) -> Response:
    profile = profile_service.get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    profile_service.delete_profile(db, profile)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{profile_id}/facts", response_model=list[ProfileFactRead])
def list_facts(profile_id: str, db: Session = Depends(get_db)) -> list[ProfileFactRead]:
    profile = profile_service.get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    facts = profile_service.list_facts(db, profile_id)
    return [ProfileFactRead.model_validate(fact) for fact in facts]


@router.post(
    "/{profile_id}/facts",
    response_model=ProfileFactRead,
    status_code=status.HTTP_201_CREATED,
)
def create_fact(
    profile_id: str,
    fact: ProfileFactCreate,
    db: Session = Depends(get_db),
) -> ProfileFactRead:
    profile = profile_service.get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    saved = profile_service.add_fact(
        db,
        profile_id,
        {
            "field_name": fact.field_name,
            "value": fact.value,
            "source": fact.source,
            "confidence": fact.confidence,
            "is_verified": fact.is_verified,
            "notes": fact.notes,
        },
    )
    return ProfileFactRead.model_validate(saved)


@router.get("/{profile_id}/facts/{fact_id}", response_model=ProfileFactRead)
def get_fact(profile_id: str, fact_id: str, db: Session = Depends(get_db)) -> ProfileFactRead:
    profile = profile_service.get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    fact = profile_service.get_fact(db, profile_id, fact_id)
    if fact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")
    return ProfileFactRead.model_validate(fact)


@router.patch("/{profile_id}/facts/{fact_id}", response_model=ProfileFactRead)
def update_fact(
    profile_id: str,
    fact_id: str,
    updates: ProfileFactUpdate,
    db: Session = Depends(get_db),
) -> ProfileFactRead:
    profile = profile_service.get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    fact = profile_service.get_fact(db, profile_id, fact_id)
    if fact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")
    payload = updates.model_dump(exclude_unset=True)
    updated = profile_service.update_fact(db, fact, payload)
    return ProfileFactRead.model_validate(updated)


@router.delete("/{profile_id}/facts/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fact(profile_id: str, fact_id: str, db: Session = Depends(get_db)) -> Response:
    profile = profile_service.get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    fact = profile_service.get_fact(db, profile_id, fact_id)
    if fact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")
    profile_service.delete_fact(db, fact)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
