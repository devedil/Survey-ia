from collections.abc import Sequence

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.profiles.models import Profile, ProfileFact, ProfileFactRevision


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


def expire_due_profile_facts(db: Session, profile_id: str) -> int:
    now = datetime.now(timezone.utc)
    facts = db.scalars(
        select(ProfileFact).where(
            ProfileFact.profile_id == profile_id,
            ProfileFact.status == "verified",
            ProfileFact.valid_until.is_not(None),
            ProfileFact.valid_until <= now,
        )
    ).all()
    for fact in facts:
        before = fact_snapshot(fact)
        fact.status = "expired"
        fact.is_verified = False
        db.add(
            ProfileFactRevision(
                fact_id=fact.id,
                change_type="expired",
                before=before,
                after=fact_snapshot(fact),
            )
        )
    if facts:
        db.commit()
    return len(facts)


def get_profile_fact(db: Session, profile_id: str, fact_id: str) -> ProfileFact | None:
    return db.get(ProfileFact, fact_id)


def create_profile_fact(db: Session, fact: ProfileFact) -> ProfileFact:
    db.add(fact)
    db.flush()
    db.add(
        ProfileFactRevision(
            fact_id=fact.id,
            change_type="created",
            before=None,
            after=fact_snapshot(fact),
        )
    )
    db.commit()
    db.refresh(fact)
    return fact


def update_profile_fact(db: Session, fact: ProfileFact, changes: dict) -> ProfileFact:
    before = fact_snapshot(fact)
    for field, value in changes.items():
        if value is None and field not in {
            "source_id",
            "confirmed_at",
            "valid_until",
            "notes",
        }:
            continue
        setattr(fact, field, value)
    db.flush()
    after = fact_snapshot(fact)
    if before != after:
        db.add(
            ProfileFactRevision(
                fact_id=fact.id,
                change_type="updated",
                before=before,
                after=after,
            )
        )
    db.commit()
    db.refresh(fact)
    return fact


def delete_profile_fact(db: Session, fact: ProfileFact) -> None:
    db.delete(fact)
    db.commit()


def fact_snapshot(fact: ProfileFact) -> dict:
    fields = (
        "field_name",
        "value",
        "source",
        "source_type",
        "source_id",
        "category",
        "status",
        "confidence",
        "is_verified",
        "sensitivity",
        "consent_to_retrieve",
        "confirmed_at",
        "valid_until",
        "notes",
    )
    snapshot = {}
    for field in fields:
        value = getattr(fact, field)
        snapshot[field] = value.isoformat() if value is not None and hasattr(value, "isoformat") else value
    return snapshot


def list_fact_revisions(db: Session, fact_id: str) -> Sequence[ProfileFactRevision]:
    return db.scalars(
        select(ProfileFactRevision)
        .where(ProfileFactRevision.fact_id == fact_id)
        .order_by(ProfileFactRevision.created_at.desc())
    ).all()


def get_fact_revision(db: Session, fact_id: str, revision_id: str) -> ProfileFactRevision | None:
    return db.scalar(
        select(ProfileFactRevision)
        .where(ProfileFactRevision.fact_id == fact_id, ProfileFactRevision.id == revision_id)
    )


def restore_fact_snapshot(db: Session, fact: ProfileFact, revision: ProfileFactRevision) -> ProfileFact:
    before = fact_snapshot(fact)
    for field, value in revision.after.items():
        if field in {"confirmed_at", "valid_until"} and value is not None:
            value = datetime.fromisoformat(value)
        setattr(fact, field, value)
    db.flush()
    db.add(
        ProfileFactRevision(
            fact_id=fact.id,
            change_type="restored",
            before=before,
            after=fact_snapshot(fact),
        )
    )
    db.commit()
    db.refresh(fact)
    return fact
