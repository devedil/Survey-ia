from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.answers.models import AnswerProposalRecord, UserFeedback
from backend.app.answers.schemas import (
    ApproveProposalRequest,
    CorrectProposalRequest,
    RejectProposalRequest,
    SupportStatus,
)
from backend.app.memory.service import DuplicateFactError, find_duplicate_facts
from backend.app.profiles.models import ProfileFact, ProfileFactRevision
from backend.app.profiles.repository import fact_snapshot


class ProposalReviewError(ValueError):
    pass


def _create_verified_fact(
    db: Session,
    proposal: AnswerProposalRecord,
    *,
    field_name: str,
    category: str,
    value: str,
    source_type: str,
    source_id: str,
    sensitivity: bool,
    consent_to_retrieve: bool,
    valid_until: datetime | None,
    notes: str | None,
) -> ProfileFact:
    if not field_name.strip() or not value.strip():
        raise ProposalReviewError("A field name and non-empty fact value are required")
    normalized_category = category.strip() or "general"
    duplicates = find_duplicate_facts(
        db,
        proposal.profile_id,
        field_name.strip(),
        normalized_category,
        value.strip(),
    )
    if duplicates:
        raise DuplicateFactError(duplicates[0].id)
    now = datetime.now(timezone.utc)
    status = "expired" if valid_until is not None and valid_until <= now else "verified"
    fact = ProfileFact(
        profile_id=proposal.profile_id,
        field_name=field_name.strip(),
        value=value.strip(),
        source="user_approved",
        source_type=source_type,
        source_id=source_id,
        category=normalized_category,
        status=status,
        confidence=1.0,
        is_verified=status == "verified",
        sensitivity=sensitivity,
        consent_to_retrieve=consent_to_retrieve and status == "verified",
        confirmed_at=now,
        valid_until=valid_until,
        notes=notes,
    )
    db.add(fact)
    db.flush()
    db.add(
        ProfileFactRevision(
            fact_id=fact.id,
            change_type="created_from_approved_proposal",
            before=None,
            after=fact_snapshot(fact),
        )
    )
    return fact


def approve_proposal(
    db: Session,
    proposal: AnswerProposalRecord,
    payload: ApproveProposalRequest,
) -> ProfileFact | None:
    if proposal.status not in {"pending", "corrected"}:
        raise ProposalReviewError("Only pending or corrected proposals can be approved")
    answer_text = proposal.answer_text.strip()
    if not answer_text or proposal.support_status != SupportStatus.SUPPORTED.value:
        raise ProposalReviewError("Only non-empty, evidence-supported proposals can be approved")
    fact = None
    if payload.save_as_fact:
        if not payload.field_name:
            raise ProposalReviewError("field_name is required when save_as_fact is true")
        fact = _create_verified_fact(
            db,
            proposal,
            field_name=payload.field_name,
            category=payload.category,
            value=answer_text,
            source_type="answer_proposal",
            source_id=proposal.id,
            sensitivity=payload.sensitivity,
            consent_to_retrieve=payload.consent_to_retrieve,
            valid_until=payload.valid_until,
            notes=payload.notes,
        )
    proposal.status = "approved"
    db.add(
        UserFeedback(
            proposal_id=proposal.id,
            feedback_type="approved",
            approved_for_memory=payload.save_as_fact,
        )
    )
    db.commit()
    if fact is not None:
        db.refresh(fact)
    db.refresh(proposal)
    return fact


def reject_proposal(
    db: Session,
    proposal: AnswerProposalRecord,
    payload: RejectProposalRequest,
) -> None:
    if proposal.status not in {"pending", "corrected"}:
        raise ProposalReviewError("Only pending or corrected proposals can be rejected")
    proposal.status = "rejected"
    db.add(
        UserFeedback(
            proposal_id=proposal.id,
            feedback_type="rejected",
            reason=payload.reason,
            approved_for_memory=False,
        )
    )
    db.commit()


def correct_proposal(
    db: Session,
    proposal: AnswerProposalRecord,
    payload: CorrectProposalRequest,
) -> ProfileFact | None:
    if proposal.status not in {"pending", "corrected"}:
        raise ProposalReviewError("Only pending or corrected proposals can be corrected")
    correction = payload.correction.strip()
    if not correction:
        raise ProposalReviewError("Correction cannot be empty")
    if payload.save_as_fact:
        if not payload.field_name:
            raise ProposalReviewError("field_name is required when save_as_fact is true")
        duplicates = find_duplicate_facts(
            db,
            proposal.profile_id,
            payload.field_name.strip(),
            payload.category.strip() or "general",
            correction,
        )
        if duplicates:
            raise DuplicateFactError(duplicates[0].id)
    feedback = UserFeedback(
        proposal_id=proposal.id,
        feedback_type="corrected",
        correction=correction,
        previous_answer=proposal.answer_text,
        approved_for_memory=payload.save_as_fact,
    )
    db.add(feedback)
    db.flush()
    proposal.answer_text = correction
    proposal.status = "corrected"
    fact = None
    if payload.save_as_fact:
        fact = _create_verified_fact(
            db,
            proposal,
            field_name=payload.field_name,
            category=payload.category,
            value=correction,
            source_type="user_correction",
            source_id=feedback.id,
            sensitivity=payload.sensitivity,
            consent_to_retrieve=payload.consent_to_retrieve,
            valid_until=payload.valid_until,
            notes=payload.notes,
        )
    db.commit()
    if fact is not None:
        db.refresh(fact)
    db.refresh(proposal)
    return fact


def restore_correction(
    db: Session,
    proposal: AnswerProposalRecord,
    feedback_id: str,
) -> None:
    if proposal.status != "corrected":
        raise ProposalReviewError("Only an unapproved corrected proposal can be restored")
    feedback = db.scalar(
        select(UserFeedback).where(
            UserFeedback.id == feedback_id,
            UserFeedback.proposal_id == proposal.id,
            UserFeedback.feedback_type == "corrected",
        )
    )
    if feedback is None:
        raise ProposalReviewError("Correction history entry not found")
    saved_correction = db.scalar(
        select(UserFeedback.id).where(
            UserFeedback.proposal_id == proposal.id,
            UserFeedback.feedback_type == "corrected",
            UserFeedback.approved_for_memory.is_(True),
        )
    )
    if saved_correction is not None:
        raise ProposalReviewError("A proposal with a correction saved to memory cannot be restored here")
    if feedback.previous_answer is None:
        raise ProposalReviewError("Correction history has no previous answer to restore")
    previous_answer = proposal.answer_text
    proposal.answer_text = feedback.previous_answer
    db.add(
        UserFeedback(
            proposal_id=proposal.id,
            feedback_type="restored",
            correction=proposal.answer_text,
            previous_answer=previous_answer,
            approved_for_memory=False,
        )
    )
    db.commit()
    db.refresh(proposal)
