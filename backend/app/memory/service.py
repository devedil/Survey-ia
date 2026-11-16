from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.answers.models import AnswerProposalRecord
from backend.app.profiles.models import Profile, ProfileFact, ProfileFactRevision
from backend.app.profiles.repository import expire_due_profile_facts
from backend.app.validation.consistency_checker import normalize_fact_value


class DuplicateFactError(ValueError):
    def __init__(self, fact_id: str):
        super().__init__(f"A verified fact with the same field and value already exists: {fact_id}")
        self.fact_id = fact_id


def search_memory(db: Session, profile_id: str, query: str, limit: int) -> list[ProfileFact]:
    expire_due_profile_facts(db, profile_id)
    terms = [term for term in normalize_fact_value(query).split() if term]
    if not terms:
        return []
    statement = select(ProfileFact).where(
        ProfileFact.profile_id == profile_id,
        ProfileFact.status == "verified",
        ProfileFact.is_verified.is_(True),
        ProfileFact.sensitivity.is_(False),
        ProfileFact.consent_to_retrieve.is_(True),
    )
    for term in terms:
        pattern = f"%{term}%"
        statement = statement.where(
            or_(
                ProfileFact.field_name.ilike(pattern),
                ProfileFact.value.ilike(pattern),
                ProfileFact.category.ilike(pattern),
            )
        )
    return list(
        db.scalars(statement.order_by(ProfileFact.updated_at.desc()).limit(limit)).all()
    )


def list_memory(
    db: Session,
    profile_id: str,
    query: str | None,
    include_expired: bool = False,
) -> list[ProfileFact]:
    expire_due_profile_facts(db, profile_id)
    statement = select(ProfileFact).where(ProfileFact.profile_id == profile_id)
    if not include_expired:
        statement = statement.where(ProfileFact.status != "expired")
    if query:
        pattern = f"%{query.strip()}%"
        statement = statement.where(
            or_(
                ProfileFact.field_name.ilike(pattern),
                ProfileFact.value.ilike(pattern),
                ProfileFact.category.ilike(pattern),
            )
        )
    return list(db.scalars(statement.order_by(ProfileFact.updated_at.desc())).all())


def find_duplicate_facts(
    db: Session,
    profile_id: str,
    field_name: str,
    category: str,
    value: str,
) -> list[ProfileFact]:
    expire_due_profile_facts(db, profile_id)
    normalized_field = normalize_fact_value(field_name)
    normalized_category = normalize_fact_value(category)
    normalized_value = normalize_fact_value(value)
    facts = db.scalars(
        select(ProfileFact).where(
            ProfileFact.profile_id == profile_id,
            ProfileFact.status == "verified",
            ProfileFact.is_verified.is_(True),
        )
    ).all()
    return [
        fact for fact in facts
        if normalize_fact_value(fact.field_name) == normalized_field
        and normalize_fact_value(fact.category) == normalized_category
        and normalize_fact_value(fact.value) == normalized_value
    ]


def export_profile_memory(db: Session, profile_id: str) -> dict:
    profile = db.get(Profile, profile_id)
    facts = db.scalars(
        select(ProfileFact)
        .options(selectinload(ProfileFact.revisions))
        .where(ProfileFact.profile_id == profile_id)
        .order_by(ProfileFact.created_at)
    ).all()
    proposals = db.scalars(
        select(AnswerProposalRecord)
        .options(
            selectinload(AnswerProposalRecord.sources),
            selectinload(AnswerProposalRecord.feedback),
        )
        .where(AnswerProposalRecord.profile_id == profile_id)
        .order_by(AnswerProposalRecord.created_at)
    ).all()
    return {
        "profile": {
            "id": profile.id,
            "name": profile.name,
            "email": profile.email,
            "created_at": profile.created_at.isoformat(),
            "updated_at": profile.updated_at.isoformat(),
        },
        "facts": [
            {
                "id": fact.id,
                "profile_id": fact.profile_id,
                "field_name": fact.field_name,
                "value": fact.value,
                "source": fact.source,
                "source_type": fact.source_type,
                "source_id": fact.source_id,
                "category": fact.category,
                "status": fact.status,
                "confidence": fact.confidence,
                "is_verified": fact.is_verified,
                "sensitivity": fact.sensitivity,
                "consent_to_retrieve": fact.consent_to_retrieve,
                "confirmed_at": fact.confirmed_at.isoformat() if fact.confirmed_at else None,
                "valid_until": fact.valid_until.isoformat() if fact.valid_until else None,
                "notes": fact.notes,
                "created_at": fact.created_at.isoformat(),
                "updated_at": fact.updated_at.isoformat(),
            }
            for fact in facts
        ],
        "fact_revisions": [
            {
                "id": revision.id,
                "fact_id": revision.fact_id,
                "change_type": revision.change_type,
                "before": revision.before,
                "after": revision.after,
                "created_at": revision.created_at.isoformat(),
            }
            for fact in facts
            for revision in fact.revisions
        ],
        "proposals": [
            {
                "id": proposal.id,
                "question_text": proposal.question_text,
                "answer_text": proposal.answer_text,
                "support_status": proposal.support_status,
                "confidence": proposal.confidence,
                "status": proposal.status,
                "answer_format": proposal.answer_format,
                "question_analysis": proposal.question_analysis,
                "created_at": proposal.created_at.isoformat(),
                "sources": [
                    {
                        "source_type": source.source_type,
                        "source_id": source.source_id,
                        "excerpt": source.excerpt,
                    }
                    for source in proposal.sources
                ],
            }
            for proposal in proposals
        ],
        "feedback": [
            {
                "id": feedback.id,
                "proposal_id": feedback.proposal_id,
                "feedback_type": feedback.feedback_type,
                "correction": feedback.correction,
                "previous_answer": feedback.previous_answer,
                "reason": feedback.reason,
                "approved_for_memory": feedback.approved_for_memory,
                "created_at": feedback.created_at.isoformat(),
            }
            for proposal in proposals
            for feedback in proposal.feedback
        ],
    }


def mark_fact_expired(db: Session, fact: ProfileFact) -> ProfileFact:
    from backend.app.profiles.repository import fact_snapshot

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
    db.commit()
    db.refresh(fact)
    return fact
