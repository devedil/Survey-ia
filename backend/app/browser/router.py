from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.call_budget import ModelCallLimitError
from backend.app.ai.dependencies import get_memory_manager, get_model_router
from backend.app.ai.model_router import ModelConfigurationError, ModelProviderError, ModelRouter
from backend.app.answers.memory_manager import MemoryManager
from backend.app.answers.repository import get_proposal
from backend.app.answers.schemas import AnswerProposal, AnswerProposeRequest, SupportStatus
from backend.app.answers.service import AnswerService
from backend.app.browser.models import BrowserAuditEvent
from backend.app.browser.schemas import (
    BrowserAuditEventRead,
    BrowserFillRead,
    BrowserFillRequest,
    BrowserInspectionRead,
    BrowserNavigateRequest,
    BrowserProposeRequest,
    BrowserSessionCreate,
    BrowserSessionRead,
)
from backend.app.browser.session_manager import (
    BrowserDependencyError,
    BrowserPolicyError,
    BrowserSessionError,
    BrowserSessionManager,
    BrowserSessionNotFound,
    public_session,
)
from backend.app.core.config import get_settings
from backend.app.core.database import get_db
from backend.app.documents.embedding_service import EmbeddingConfigurationError
from backend.app.profiles.repository import get_profile

router = APIRouter(prefix="/browser", tags=["browser"])


def get_browser_session_manager(request: Request) -> BrowserSessionManager:
    manager = getattr(request.app.state, "browser_session_manager", None)
    if manager is None:
        manager = BrowserSessionManager(get_settings().browser_allowed_origins)
        request.app.state.browser_session_manager = manager
    return manager


def _record_event(
    db: Session,
    session_id: str,
    profile_id: str,
    action: str,
    domain: str | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        BrowserAuditEvent(
            session_id=session_id,
            profile_id=profile_id,
            action=action,
            domain=domain,
            details=details or {},
        )
    )
    db.commit()


def _session_or_404(manager: BrowserSessionManager, session_id: str):
    try:
        return manager.status(session_id)
    except BrowserSessionNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/test-site", response_class=HTMLResponse, include_in_schema=False)
def local_test_site() -> HTMLResponse:
    return HTMLResponse(
        """<!doctype html>
<html lang="es">
<head><meta charset="utf-8"><title>Formulario local de prueba</title></head>
<body>
  <main>
    <h1>Formulario local de prueba</h1>
    <form method="post">
      <label for="city">¿En qué ciudad vives?</label>
      <input id="city" name="city" type="text" maxlength="80" required>

      <label for="experience">¿Cuántos años de experiencia tienes?</label>
      <input id="experience" name="experience" type="number" min="0" max="80">

      <label for="sector">¿En qué sector trabajas?</label>
      <select id="sector" name="sector" required>
        <option value="">Selecciona un sector</option>
        <option value="technology">Tecnología</option>
        <option value="education">Educación</option>
        <option value="health">Salud</option>
      </select>

      <fieldset>
        <legend>¿Trabajas actualmente?</legend>
        <label><input type="radio" name="employed" value="yes"> Sí</label>
        <label><input type="radio" name="employed" value="no"> No</label>
      </fieldset>

      <button type="submit">Enviar (no pulsar)</button>
    </form>
  </main>
</body>
</html>"""
    )


@router.post("/sessions", response_model=BrowserSessionRead, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: BrowserSessionCreate,
    db: Session = Depends(get_db),
    manager: BrowserSessionManager = Depends(get_browser_session_manager),
) -> BrowserSessionRead:
    if get_profile(db, payload.profile_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    try:
        session = manager.create(payload.profile_id)
    except BrowserDependencyError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except BrowserSessionError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    _record_event(db, session.session_id, session.profile_id, "session_created")
    return BrowserSessionRead.model_validate(public_session(session))


@router.get("/sessions/{session_id}", response_model=BrowserSessionRead)
def get_session(
    session_id: str,
    manager: BrowserSessionManager = Depends(get_browser_session_manager),
) -> BrowserSessionRead:
    session = _session_or_404(manager, session_id)
    return BrowserSessionRead.model_validate(public_session(session))


@router.post("/sessions/{session_id}/navigate", response_model=BrowserSessionRead)
def navigate(
    session_id: str,
    payload: BrowserNavigateRequest,
    db: Session = Depends(get_db),
    manager: BrowserSessionManager = Depends(get_browser_session_manager),
) -> BrowserSessionRead:
    session = _session_or_404(manager, session_id)
    try:
        session = manager.navigate(session_id, payload.url)
    except BrowserPolicyError as error:
        _record_event(
            db,
            session_id,
            session.profile_id,
            "navigation_blocked",
            error.domain,
            {"status": "blocked"},
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except BrowserSessionError as error:
        _record_event(
            db,
            session_id,
            session.profile_id,
            "navigation_failed",
            details={"status": "failed"},
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    domain = urlsplit(session.current_url).hostname if session.current_url else None
    _record_event(db, session_id, session.profile_id, "navigated", domain)
    return BrowserSessionRead.model_validate(public_session(session))


@router.post("/sessions/{session_id}/inspect", response_model=BrowserInspectionRead)
def inspect(
    session_id: str,
    db: Session = Depends(get_db),
    manager: BrowserSessionManager = Depends(get_browser_session_manager),
) -> BrowserInspectionRead:
    session = _session_or_404(manager, session_id)
    try:
        session, title, controls = manager.inspect(session_id)
    except BrowserPolicyError as error:
        _record_event(
            db,
            session_id,
            session.profile_id,
            "captcha_detected",
            error.domain,
            {"status": "stopped"},
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except BrowserSessionError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    domain = urlsplit(session.current_url).hostname if session.current_url else None
    _record_event(
        db,
        session_id,
        session.profile_id,
        "page_inspected",
        domain,
        {"control_count": len(controls)},
    )
    return BrowserInspectionRead(
        url=public_session(session)["current_url"] or "",
        title=title,
        controls=controls,
    )


@router.post("/sessions/{session_id}/propose", response_model=AnswerProposal)
def propose_for_control(
    session_id: str,
    payload: BrowserProposeRequest,
    db: Session = Depends(get_db),
    manager: BrowserSessionManager = Depends(get_browser_session_manager),
    model_router: ModelRouter = Depends(get_model_router),
    memory_manager: MemoryManager = Depends(get_memory_manager),
) -> AnswerProposal:
    session = _session_or_404(manager, session_id)
    try:
        _, control = manager.control_for_proposal(session_id, payload.control_id)
    except BrowserSessionError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if get_profile(db, session.profile_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    try:
        proposal = AnswerService(model_router, memory_manager).propose(
            db,
            AnswerProposeRequest(
                profile_id=session.profile_id,
                question_text=control.question_text,
                options=[option["label"] for option in control.options],
                required=control.required,
                max_length=control.max_length,
            ),
        )
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
    _record_event(
        db,
        session_id,
        session.profile_id,
        "proposal_created",
        urlsplit(session.current_url).hostname if session.current_url else None,
        {"control_id": payload.control_id, "proposal_id": proposal.proposal_id},
    )
    return proposal


@router.post(
    "/sessions/{session_id}/fill-approved",
    response_model=BrowserFillRead,
)
def fill_approved(
    session_id: str,
    payload: BrowserFillRequest,
    db: Session = Depends(get_db),
    manager: BrowserSessionManager = Depends(get_browser_session_manager),
) -> BrowserFillRead:
    session = _session_or_404(manager, session_id)
    proposal = get_proposal(db, session.profile_id, payload.proposal_id)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Answer proposal not found")
    if proposal.status != "approved" or proposal.support_status != SupportStatus.SUPPORTED.value:
        _record_event(
            db,
            session_id,
            session.profile_id,
            "fill_rejected",
            urlsplit(session.current_url).hostname if session.current_url else None,
            {"reason": "proposal_not_approved", "proposal_id": proposal.id},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only an explicitly approved, evidence-supported proposal can be filled",
        )
    try:
        session, control = manager.control_for_proposal(session_id, payload.control_id)
        if proposal.question_text.strip().casefold() != control.question_text.strip().casefold():
            raise BrowserSessionError("Approved proposal does not match the selected form question")
        manager.fill_approved(session_id, payload.control_id, proposal.answer_text)
    except BrowserSessionError as error:
        _record_event(
            db,
            session_id,
            session.profile_id,
            "fill_rejected",
            urlsplit(session.current_url).hostname if session.current_url else None,
            {"reason": "control_or_value_validation_failed", "proposal_id": proposal.id},
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    _record_event(
        db,
        session_id,
        session.profile_id,
        "approved_value_filled",
        urlsplit(session.current_url).hostname if session.current_url else None,
        {"control_id": payload.control_id, "proposal_id": proposal.id, "verified": True},
    )
    return BrowserFillRead(
        session_id=session_id,
        control_id=payload.control_id,
        proposal_id=proposal.id,
        verified=True,
        status="filled",
    )


@router.post("/sessions/{session_id}/stop", response_model=BrowserSessionRead)
def stop_session(
    session_id: str,
    db: Session = Depends(get_db),
    manager: BrowserSessionManager = Depends(get_browser_session_manager),
) -> BrowserSessionRead:
    session = _session_or_404(manager, session_id)
    session = manager.stop(session_id)
    _record_event(
        db,
        session_id,
        session.profile_id,
        "session_stopped",
        urlsplit(session.current_url).hostname if session.current_url else None,
    )
    return BrowserSessionRead.model_validate(public_session(session))


@router.get("/audit/events", response_model=list[BrowserAuditEventRead])
def list_audit_events(
    profile_id: str | None = None,
    session_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[BrowserAuditEventRead]:
    statement = select(BrowserAuditEvent).order_by(BrowserAuditEvent.created_at.desc())
    if profile_id is not None:
        statement = statement.where(BrowserAuditEvent.profile_id == profile_id)
    if session_id is not None:
        statement = statement.where(BrowserAuditEvent.session_id == session_id)
    events = db.scalars(statement.limit(limit)).all()
    return [BrowserAuditEventRead.model_validate(event) for event in events]
