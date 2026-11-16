from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.ai.call_budget import ModelCallLimitError
from backend.app.ai.dependencies import get_memory_manager, get_model_router
from backend.app.ai.model_router import ModelConfigurationError, ModelProviderError, ModelRouter
from backend.app.answers.memory_manager import MemoryManager
from backend.app.answers.models import AnswerProposalRecord
from backend.app.answers.repository import get_proposal, list_proposals
from backend.app.answers.review_service import (
    ProposalReviewError,
    approve_proposal,
    correct_proposal,
    reject_proposal,
    restore_correction,
)
from backend.app.answers.schemas import (
    AnswerProposal,
    AnswerProposalHistoryItem,
    AnswerProposeRequest,
    ApproveProposalRequest,
    CorrectProposalRequest,
    ProposalStatus,
    RejectProposalRequest,
    UserFeedbackRead,
)
from backend.app.answers.service import AnswerService
from backend.app.core.database import get_db
from backend.app.documents.embedding_service import EmbeddingConfigurationError
from backend.app.memory.service import DuplicateFactError
from backend.app.profiles.repository import get_profile

router = APIRouter(prefix="/answers", tags=["answers"])


def _read_proposal(
    proposal: AnswerProposalRecord,
    created_fact_id: str | None = None,
) -> AnswerProposal:
    return AnswerProposal(
        proposal_id=proposal.id,
        created_fact_id=created_fact_id,
        status=ProposalStatus(proposal.status),
        suggested_answer=proposal.answer_text,
        support_status=proposal.support_status,
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


@router.post("/propose", response_model=AnswerProposal)
def propose(
    payload: AnswerProposeRequest,
    db: Session = Depends(get_db),
    model_router: ModelRouter = Depends(get_model_router),
    memory_manager: MemoryManager = Depends(get_memory_manager),
) -> AnswerProposal:
    if get_profile(db, payload.profile_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    try:
        return AnswerService(model_router, memory_manager).propose(db, payload)
    except ModelConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except EmbeddingConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except ModelProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    except ModelCallLimitError as error:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Model returned an invalid answer proposal") from error


@router.get("", response_model=list[AnswerProposalHistoryItem])
def proposal_history(
    profile_id: str,
    status_filter: ProposalStatus | None = None,
    db: Session = Depends(get_db),
) -> list[AnswerProposalHistoryItem]:
    if get_profile(db, profile_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    proposals = list_proposals(
        db,
        profile_id,
        status_filter.value if status_filter else None,
    )
    return [
        AnswerProposalHistoryItem(
            proposal_id=proposal.id,
            profile_id=proposal.profile_id,
            question_text=proposal.question_text,
            suggested_answer=proposal.answer_text,
            support_status=proposal.support_status,
            confidence=proposal.confidence,
            status=proposal.status,
            answer_format=proposal.answer_format,
            created_at=proposal.created_at,
            sources=[
                {
                    "source_type": source.source_type,
                    "source_id": source.source_id,
                    "excerpt": source.excerpt,
                }
                for source in proposal.sources
            ],
        )
        for proposal in proposals
    ]


@router.get("/{proposal_id}", response_model=AnswerProposal)
def proposal_detail(
    proposal_id: str,
    profile_id: str,
    db: Session = Depends(get_db),
) -> AnswerProposal:
    if get_profile(db, profile_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    proposal = get_proposal(db, profile_id, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Answer proposal not found")
    return _read_proposal(proposal)


@router.get("/{proposal_id}/history", response_model=list[UserFeedbackRead])
def proposal_feedback_history(
    proposal_id: str,
    profile_id: str,
    db: Session = Depends(get_db),
) -> list[UserFeedbackRead]:
    proposal = get_proposal(db, profile_id, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Answer proposal not found")
    return [UserFeedbackRead.model_validate(entry) for entry in proposal.feedback]


@router.post("/{proposal_id}/approve", response_model=AnswerProposal)
def approve(
    proposal_id: str,
    payload: ApproveProposalRequest,
    profile_id: str,
    db: Session = Depends(get_db),
) -> AnswerProposal:
    proposal = get_proposal(db, profile_id, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Answer proposal not found")
    try:
        fact = approve_proposal(db, proposal, payload)
    except ProposalReviewError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except DuplicateFactError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(error), "existing_fact_id": error.fact_id},
        ) from error
    return _read_proposal(proposal, fact.id if fact else None)


@router.post("/{proposal_id}/restore/{feedback_id}", response_model=AnswerProposal)
def restore(
    proposal_id: str,
    feedback_id: str,
    profile_id: str,
    db: Session = Depends(get_db),
) -> AnswerProposal:
    proposal = get_proposal(db, profile_id, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Answer proposal not found")
    try:
        restore_correction(db, proposal, feedback_id)
    except ProposalReviewError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return _read_proposal(proposal)


@router.post("/{proposal_id}/reject", response_model=AnswerProposal)
def reject(
    proposal_id: str,
    payload: RejectProposalRequest,
    profile_id: str,
    db: Session = Depends(get_db),
) -> AnswerProposal:
    proposal = get_proposal(db, profile_id, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Answer proposal not found")
    try:
        reject_proposal(db, proposal, payload)
    except ProposalReviewError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return _read_proposal(proposal)


@router.post("/{proposal_id}/correct", response_model=AnswerProposal)
def correct(
    proposal_id: str,
    payload: CorrectProposalRequest,
    profile_id: str,
    db: Session = Depends(get_db),
) -> AnswerProposal:
    proposal = get_proposal(db, profile_id, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Answer proposal not found")
    try:
        fact = correct_proposal(db, proposal, payload)
    except ProposalReviewError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except DuplicateFactError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(error), "existing_fact_id": error.fact_id},
        ) from error
    return _read_proposal(proposal, fact.id if fact else None)
