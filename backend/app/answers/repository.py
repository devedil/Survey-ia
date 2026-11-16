from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.answers.models import AnswerProposalRecord


def get_proposal(db: Session, profile_id: str, proposal_id: str) -> AnswerProposalRecord | None:
    return db.scalar(
        select(AnswerProposalRecord)
        .options(
            selectinload(AnswerProposalRecord.sources),
            selectinload(AnswerProposalRecord.feedback),
        )
        .where(
            AnswerProposalRecord.profile_id == profile_id,
            AnswerProposalRecord.id == proposal_id,
        )
    )


def list_proposals(
    db: Session,
    profile_id: str,
    status_filter: str | None = None,
) -> Sequence[AnswerProposalRecord]:
    statement = (
        select(AnswerProposalRecord)
        .options(
            selectinload(AnswerProposalRecord.sources),
            selectinload(AnswerProposalRecord.feedback),
        )
        .where(AnswerProposalRecord.profile_id == profile_id)
        .order_by(AnswerProposalRecord.created_at.desc())
    )
    if status_filter:
        statement = statement.where(AnswerProposalRecord.status == status_filter)
    return db.scalars(statement).all()
