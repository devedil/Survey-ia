from backend.app.answers.models import AnswerProposalRecord
from backend.app.answers.schemas import (
    AnswerProposal,
    ProposalStatus,
    SupportStatus,
)


def answer_proposal_from_record(
    proposal: AnswerProposalRecord,
    created_fact_id: str | None = None,
) -> AnswerProposal:
    return AnswerProposal(
        proposal_id=proposal.id,
        created_fact_id=created_fact_id,
        status=ProposalStatus(proposal.status),
        suggested_answer=proposal.answer_text,
        support_status=SupportStatus(proposal.support_status),
        confidence=proposal.confidence,
        sources=[
            {
                "source_type": source.source_type,
                "source_id": source.source_id,
                "excerpt": source.excerpt,
            }
            for source in proposal.sources
        ],
        needs_user_input=proposal.needs_user_input,
        needs_review=proposal.needs_review and proposal.status == "pending",
        review_reason=proposal.review_reason,
        answer_format=proposal.answer_format,
        question_analysis=proposal.question_analysis,
    )
