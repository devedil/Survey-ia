from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.profiles.models import Profile, ProfileFact
from backend.app.profiles.repository import (
    create_profile,
    create_profile_fact,
    delete_profile,
    delete_profile_fact,
    get_profile,
    get_profile_fact,
    get_fact_revision,
    list_fact_revisions,
    list_profile_facts,
    list_profiles,
    update_profile,
    update_profile_fact,
    restore_fact_snapshot,
)


class ProfileService:
    def list_profiles(self, db: Session) -> list[Profile]:
        return list(list_profiles(db))

    def get_profile(self, db: Session, profile_id: str) -> Profile | None:
        return get_profile(db, profile_id)

    def create_profile(self, db: Session, name: str, email: str | None) -> Profile:
        profile = Profile(name=name, email=email)
        return create_profile(db, profile)

    def update_profile(self, db: Session, profile: Profile, payload: dict) -> Profile:
        return update_profile(db, profile, payload)

    def delete_profile(self, db: Session, profile: Profile) -> None:
        delete_profile(db, profile)

    def list_facts(self, db: Session, profile_id: str) -> list[ProfileFact]:
        return list(list_profile_facts(db, profile_id))

    def add_fact(self, db: Session, profile_id: str, payload: dict) -> ProfileFact:
        status = payload.get("status")
        if status is None:
            status = "verified" if payload.get("is_verified", True) else "pending"
            payload["status"] = status
        elif status not in {"pending", "verified", "rejected", "expired"}:
            raise ValueError("Invalid fact status")
        payload["is_verified"] = status == "verified"
        if payload["is_verified"]:
            payload.setdefault("confirmed_at", datetime.now(timezone.utc))
        fact = ProfileFact(profile_id=profile_id, **payload)
        return create_profile_fact(db, fact)

    def get_fact(self, db: Session, profile_id: str, fact_id: str) -> ProfileFact | None:
        fact = get_profile_fact(db, profile_id, fact_id)
        if fact and fact.profile_id != profile_id:
            return None
        return fact

    def update_fact(self, db: Session, fact: ProfileFact, payload: dict) -> ProfileFact:
        if "status" in payload and payload["status"] is not None:
            payload["is_verified"] = payload["status"] == "verified"
            payload.setdefault(
                "confirmed_at",
                datetime.now(timezone.utc) if payload["is_verified"] else None,
            )
        elif "is_verified" in payload:
            payload["status"] = "verified" if payload["is_verified"] else "pending"
            payload.setdefault(
                "confirmed_at",
                datetime.now(timezone.utc) if payload["is_verified"] else None,
            )
        return update_profile_fact(db, fact, payload)

    def list_fact_history(self, db: Session, fact_id: str):
        return list(list_fact_revisions(db, fact_id))

    def restore_fact(self, db: Session, fact: ProfileFact, revision_id: str) -> ProfileFact | None:
        revision = get_fact_revision(db, fact.id, revision_id)
        if revision is None:
            return None
        return restore_fact_snapshot(db, fact, revision)

    def delete_fact(self, db: Session, fact: ProfileFact) -> None:
        delete_profile_fact(db, fact)


profile_service = ProfileService()
