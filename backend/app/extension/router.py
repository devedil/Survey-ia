import ipaddress
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.ai.call_budget import ModelCallLimitError
from backend.app.ai.dependencies import get_memory_manager, get_model_router
from backend.app.ai.model_router import ModelConfigurationError, ModelProviderError, ModelRouter
from backend.app.answers.memory_manager import MemoryManager
from backend.app.answers.models import AnswerProposalRecord
from backend.app.answers.presenter import answer_proposal_from_record
from backend.app.answers.repository import get_proposal
from backend.app.answers.review_service import (
    ProposalReviewError,
    approve_proposal,
    correct_proposal,
    reject_proposal,
)
from backend.app.answers.schemas import (
    AnswerProposal,
    AnswerProposeRequest,
    ApproveProposalRequest,
    CorrectProposalRequest,
    RejectProposalRequest,
)
from backend.app.answers.service import AnswerService
from backend.app.core.database import get_db
from backend.app.documents.embedding_service import EmbeddingConfigurationError
from backend.app.extension.auth import require_extension_api_token
from backend.app.extension.models import ChromeExtensionAuditEvent
from backend.app.extension.schemas import (
    ExtensionAuditCreate,
    ExtensionAuditRead,
    ExtensionCorrectionRequest,
    ExtensionProfileRead,
    ExtensionProposalAction,
    ExtensionProposeRequest,
    ExtensionRejectRequest,
)
from backend.app.memory.service import DuplicateFactError
from backend.app.profiles.repository import get_profile
from backend.app.profiles.service import profile_service

router = APIRouter(
    prefix="/chrome-extension",
    tags=["chrome-extension"],
    dependencies=[Depends(require_extension_api_token)],
)


def _validate_survey_origin(origin: str) -> str:
    try:
        parsed = urlsplit(origin)
        hostname = parsed.hostname
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or hostname is None
        ):
            raise ValueError
        if parsed.scheme == "https":
            parsed.port
            return f"https://{parsed.netloc}"
        if parsed.scheme == "http":
            try:
                loopback = hostname.casefold() == "localhost" or ipaddress.ip_address(
                    hostname
                ).is_loopback
            except ValueError:
                loopback = False
            if loopback:
                parsed.port
                return f"http://{parsed.netloc}"
    except ValueError:
        pass
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Origin must be an exact HTTPS origin or an HTTP loopback origin",
    )


def _record_event(
    db: Session,
    profile_id: str,
    origin: str,
    action: str,
    control_type: str | None = None,
) -> None:
    db.add(
        ChromeExtensionAuditEvent(
            profile_id=profile_id,
            origin=_validate_survey_origin(origin),
            action=action,
            control_type=control_type,
        )
    )
    db.commit()


def _proposal_or_404(
    db: Session,
    profile_id: str,
    proposal_id: str,
) -> AnswerProposalRecord:
    proposal = get_proposal(db, profile_id, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Answer proposal not found")
    return proposal


@router.get("/profiles", response_model=list[ExtensionProfileRead])
def list_extension_profiles(db: Session = Depends(get_db)) -> list[ExtensionProfileRead]:
    return [
        ExtensionProfileRead(id=profile.id, name=profile.name)
        for profile in profile_service.list_profiles(db)
    ]


@router.post("/proposals", response_model=AnswerProposal)
def propose_extension_answer(
    payload: ExtensionProposeRequest,
    db: Session = Depends(get_db),
    model_router: ModelRouter = Depends(get_model_router),
    memory_manager: MemoryManager = Depends(get_memory_manager),
) -> AnswerProposal:
    origin = _validate_survey_origin(payload.origin)
    if get_profile(db, payload.profile_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    request = AnswerProposeRequest(
        profile_id=payload.profile_id,
        question_text=payload.question_text,
        options=payload.options,
        required=payload.required,
        max_length=payload.max_length,
    )
    try:
        proposal = AnswerService(model_router, memory_manager).propose(db, request)
    except ModelConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except EmbeddingConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except ModelProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    except ModelCallLimitError as error:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Model returned an invalid answer proposal",
        ) from error
    _record_event(db, payload.profile_id, origin, "proposal_created")
    return proposal


@router.post("/proposals/{proposal_id}/correct", response_model=AnswerProposal)
def correct_extension_proposal(
    proposal_id: str,
    payload: ExtensionCorrectionRequest,
    db: Session = Depends(get_db),
) -> AnswerProposal:
    origin = _validate_survey_origin(payload.origin)
    proposal = _proposal_or_404(db, payload.profile_id, proposal_id)
    try:
        correct_proposal(
            db,
            proposal,
            CorrectProposalRequest(correction=payload.correction, save_as_fact=False),
        )
    except ProposalReviewError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except DuplicateFactError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(error), "existing_fact_id": error.fact_id},
        ) from error
    _record_event(db, payload.profile_id, origin, "proposal_corrected")
    return answer_proposal_from_record(proposal)


@router.post("/proposals/{proposal_id}/approve", response_model=AnswerProposal)
def approve_extension_proposal(
    proposal_id: str,
    payload: ExtensionProposalAction,
    db: Session = Depends(get_db),
) -> AnswerProposal:
    origin = _validate_survey_origin(payload.origin)
    proposal = _proposal_or_404(db, payload.profile_id, proposal_id)
    try:
        approve_proposal(db, proposal, ApproveProposalRequest(save_as_fact=False))
    except ProposalReviewError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    _record_event(db, payload.profile_id, origin, "proposal_approved")
    return answer_proposal_from_record(proposal)


@router.post("/proposals/{proposal_id}/reject", response_model=AnswerProposal)
def reject_extension_proposal(
    proposal_id: str,
    payload: ExtensionRejectRequest,
    db: Session = Depends(get_db),
) -> AnswerProposal:
    origin = _validate_survey_origin(payload.origin)
    proposal = _proposal_or_404(db, payload.profile_id, proposal_id)
    try:
        reject_proposal(db, proposal, RejectProposalRequest(reason=payload.reason))
    except ProposalReviewError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    _record_event(db, payload.profile_id, origin, "proposal_rejected")
    return answer_proposal_from_record(proposal)


@router.post("/audit", response_model=ExtensionAuditRead, status_code=status.HTTP_201_CREATED)
def record_extension_event(
    payload: ExtensionAuditCreate,
    db: Session = Depends(get_db),
) -> ExtensionAuditRead:
    if get_profile(db, payload.profile_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    event = ChromeExtensionAuditEvent(
        profile_id=payload.profile_id,
        origin=_validate_survey_origin(payload.origin),
        action=payload.action,
        control_type=payload.control_type,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return ExtensionAuditRead.model_validate(event)
