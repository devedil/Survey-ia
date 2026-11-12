from sqlalchemy.orm import Session

from backend.app.profiles.models import Profile, ProfileFact
from backend.app.profiles.repository import (
    create_profile,
    create_profile_fact,
    delete_profile,
    delete_profile_fact,
    get_profile,
    get_profile_fact,
    list_profile_facts,
    list_profiles,
    update_profile,
    update_profile_fact,
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
        fact = ProfileFact(profile_id=profile_id, **payload)
        return create_profile_fact(db, fact)

    def get_fact(self, db: Session, profile_id: str, fact_id: str) -> ProfileFact | None:
        fact = get_profile_fact(db, profile_id, fact_id)
        if fact and fact.profile_id != profile_id:
            return None
        return fact

    def update_fact(self, db: Session, fact: ProfileFact, payload: dict) -> ProfileFact:
        return update_profile_fact(db, fact, payload)

    def delete_fact(self, db: Session, fact: ProfileFact) -> None:
        delete_profile_fact(db, fact)


profile_service = ProfileService()
