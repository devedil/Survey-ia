from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.profiles.models import Profile, ProfileFact


def list_profiles(db: Session) -> Sequence[Profile]:
    return db.scalars(select(Profile).order_by(Profile.created_at.desc())).all()


def get_profile(db: Session, profile_id: str) -> Profile | None:
    return db.get(Profile, profile_id)


def create_profile(db: Session, profile: Profile) -> Profile:
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def update_profile(db: Session, profile: Profile, changes: dict) -> Profile:
    for field, value in changes.items():
        if value is not None:
            setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return profile


def delete_profile(db: Session, profile: Profile) -> None:
    db.delete(profile)
    db.commit()


def list_profile_facts(db: Session, profile_id: str) -> Sequence[ProfileFact]:
    return db.scalars(
        select(ProfileFact)
        .where(ProfileFact.profile_id == profile_id)
        .order_by(ProfileFact.created_at.desc())
    ).all()


def get_profile_fact(db: Session, profile_id: str, fact_id: str) -> ProfileFact | None:
    return db.get(ProfileFact, fact_id)


def create_profile_fact(db: Session, fact: ProfileFact) -> ProfileFact:
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return fact


def update_profile_fact(db: Session, fact: ProfileFact, changes: dict) -> ProfileFact:
    for field, value in changes.items():
        if value is not None:
            setattr(fact, field, value)
    db.commit()
    db.refresh(fact)
    return fact


def delete_profile_fact(db: Session, fact: ProfileFact) -> None:
    db.delete(fact)
    db.commit()
