import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.ai.dependencies import get_memory_manager, get_model_router
from backend.app.browser.router import get_browser_session_manager
from backend.app.browser.session_manager import (
    BrowserPolicyError,
    BrowserSessionManager,
    _Control,
)
from backend.app.core.config import Settings, get_settings
from backend.app.extension import auth as extension_auth
from backend.app.core.database import Base, get_db
from backend.app.main import app
from backend.app.answers.models import AnswerProposalRecord
from backend.app.profiles.models import ProfileFact


class FakeBrowserSessionManager:
    def __init__(self):
        self.policy = BrowserSessionManager("http://127.0.0.1:8000")
        self.sessions = {}
        self.filled_answers = []
        self.control = _Control(
            control_id="control-0",
            question_text="¿En qué ciudad vives?",
            control_type="text",
            required=True,
            max_length=80,
            indices=[0],
            options=[],
            signature="city-field",
        )

    def create(self, profile_id: str):
        session_id = str(uuid.uuid4())
        session = SimpleNamespace(
            session_id=session_id,
            profile_id=profile_id,
            created_at=datetime.now(timezone.utc),
            status="active",
            current_url=None,
        )
        self.sessions[session_id] = session
        return session

    def status(self, session_id: str):
        if session_id not in self.sessions:
            from backend.app.browser.session_manager import BrowserSessionNotFound

            raise BrowserSessionNotFound("Browser session not found")
        return self.sessions[session_id]

    def navigate(self, session_id: str, url: str):
        session = self.status(session_id)
        if not self.policy._is_allowed_url(url):
            session.status = "blocked"
            raise BrowserPolicyError(
                "Navigation is outside the local test-site allowlist",
                self.policy.domain_for_url(url),
            )
        session.current_url = url
        return session

    def inspect(self, session_id: str):
        session = self.status(session_id)
        return session, "Formulario local de prueba", [self.control.read()]

    def control_for_proposal(self, session_id: str, control_id: str):
        session = self.status(session_id)
        if session.status != "active" or control_id != self.control.control_id:
            from backend.app.browser.session_manager import BrowserSessionError

            raise BrowserSessionError("Control is not available")
        return session, self.control

    def fill_approved(self, session_id: str, control_id: str, answer: str):
        self.control_for_proposal(session_id, control_id)
        self.filled_answers.append(answer)
        return self.status(session_id)

    def stop(self, session_id: str):
        session = self.status(session_id)
        session.status = "stopped"
        return session


class FakeModelRouter:
    settings = get_settings()

    def complete_json(
        self,
        db,
        *,
        profile_id,
        operation,
        system_prompt,
        user_payload,
        call_budget=None,
    ):
        return SimpleNamespace(
            data={
                "question_text": user_payload["question_text"],
                "instructions": [],
                "question_type": "free_text",
                "options": user_payload["options"],
                "required": user_payload["required"],
                "max_length": user_payload["max_length"],
                "language": "es",
                "requests_personal_information": False,
                "needs_additional_context": False,
            }
        )


class FakeMemoryManager:
    def retrieve(self, db, profile_id, query, **kwargs):
        return []


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    manager = FakeBrowserSessionManager()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_browser_session_manager] = lambda: manager
    app.dependency_overrides[get_model_router] = lambda: FakeModelRouter()
    app.dependency_overrides[get_memory_manager] = lambda: FakeMemoryManager()
    with TestClient(app) as test_client:
        test_client.app.state.test_session = test_session
        test_client.app.state.browser_manager = manager
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def _create_profile(client: TestClient) -> str:
    response = client.post("/api/v1/profiles", json={"name": "Browser test"})
    assert response.status_code == 201
    return response.json()["id"]


def _create_session(client: TestClient, profile_id: str) -> str:
    response = client.post(
        "/api/v1/browser/sessions",
        json={"profile_id": profile_id},
    )
    assert response.status_code == 201
    return response.json()["session_id"]


def test_browser_routes_propose_from_inspected_control_and_reject_unapproved_fill(
    client: TestClient,
) -> None:
    profile_id = _create_profile(client)
    session_id = _create_session(client, profile_id)
    target_url = "http://127.0.0.1:8000/api/v1/browser/test-site"

    navigated = client.post(
        f"/api/v1/browser/sessions/{session_id}/navigate",
        json={"url": target_url},
    )
    assert navigated.status_code == 200
    inspection = client.post(f"/api/v1/browser/sessions/{session_id}/inspect")
    assert inspection.status_code == 200
    assert inspection.json()["controls"][0]["question_text"] == "¿En qué ciudad vives?"

    proposed = client.post(
        f"/api/v1/browser/sessions/{session_id}/propose",
        json={"control_id": "control-0"},
    )
    assert proposed.status_code == 200
    assert proposed.json()["support_status"] == "insufficient"

    db_factory = client.app.state.test_session
    with db_factory() as db:
        proposal = AnswerProposalRecord(
            profile_id=profile_id,
            question_text="¿En qué ciudad vives?",
            answer_text="Madrid",
            support_status="supported",
            confidence=0.9,
            status="pending",
            answer_format="text",
            question_analysis={"question_text": "¿En qué ciudad vives?"},
            needs_user_input=False,
            needs_review=True,
        )
        db.add(proposal)
        db.commit()
        db.refresh(proposal)
        proposal_id = proposal.id

    payload = {"control_id": "control-0", "proposal_id": proposal_id}
    pending = client.post(
        f"/api/v1/browser/sessions/{session_id}/fill-approved",
        json=payload,
    )
    assert pending.status_code == 409
    assert client.app.state.browser_manager.filled_answers == []

    with db_factory() as db:
        proposal = db.get(AnswerProposalRecord, proposal_id)
        proposal.status = "approved"
        db.commit()

    approved = client.post(
        f"/api/v1/browser/sessions/{session_id}/fill-approved",
        json={**payload, "answer_text": "Unapproved client value"},
    )
    assert approved.status_code == 200
    assert approved.json()["verified"] is True
    assert client.app.state.browser_manager.filled_answers == ["Madrid"]
    audit = client.get(
        "/api/v1/browser/audit/events",
        params={"session_id": session_id},
    )
    assert audit.status_code == 200
    assert [event["action"] for event in audit.json()][0] == "approved_value_filled"
    assert "Madrid" not in audit.text


def test_browser_blocks_external_domain_and_persists_block_event(client: TestClient) -> None:
    profile_id = _create_profile(client)
    session_id = _create_session(client, profile_id)

    response = client.post(
        f"/api/v1/browser/sessions/{session_id}/navigate",
        json={"url": "https://example.com/"},
    )

    assert response.status_code == 403
    session = client.get(f"/api/v1/browser/sessions/{session_id}")
    assert session.json()["status"] == "blocked"
    audit = client.get(
        "/api/v1/browser/audit/events",
        params={"session_id": session_id},
    )
    assert audit.status_code == 200
    assert audit.json()[0]["action"] == "navigation_blocked"
    assert audit.json()[0]["domain"] == "example.com"


def test_browser_origin_policy_allows_only_the_local_test_form() -> None:
    manager = BrowserSessionManager(
        "http://127.0.0.1:8000,http://localhost:8000",
    )

    assert manager._is_allowed_url("http://127.0.0.1:8000/api/v1/browser/test-site")
    assert manager._is_allowed_url("http://localhost:8000/api/v1/browser/test-site")
    assert not manager._is_allowed_url("https://example.com/api/v1/browser/test-site")
    assert not manager._is_allowed_url("http://127.0.0.1:8000/api/v1/profiles")
    assert not manager._is_allowed_url("http://127.0.0.1:8000/api/v1/browser/test-site?next=x")


def test_local_test_form_is_read_only_for_automation(client: TestClient) -> None:
    response = client.get("/api/v1/browser/test-site")

    assert response.status_code == 200
    assert "¿En qué ciudad vives?" in response.text
    assert 'type="submit"' in response.text


def _extension_headers(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    token = "test-extension-token-" + ("x" * 32)
    monkeypatch.setattr(
        extension_auth,
        "get_settings",
        lambda: SimpleNamespace(chrome_extension_api_token=SecretStr(token)),
    )
    return {"Authorization": f"Bearer {token}"}


def test_extension_routes_require_token_and_minimize_profile_data(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_response = client.post(
        "/api/v1/profiles",
        json={"name": "Real profile", "email": "private@example.test"},
    )
    profile_id = profile_response.json()["id"]
    headers = _extension_headers(monkeypatch)

    unauthorized = client.get("/api/v1/chrome-extension/profiles")
    assert unauthorized.status_code == 401

    profiles = client.get(
        "/api/v1/chrome-extension/profiles",
        headers=headers,
    )
    assert profiles.status_code == 200
    assert profiles.json() == [{"id": profile_id, "name": "Real profile"}]
    assert "private@example.test" not in profiles.text


def test_extension_proposal_is_authenticated_and_audit_omits_question_text(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_id = _create_profile(client)
    headers = _extension_headers(monkeypatch)
    payload = {
        "profile_id": profile_id,
        "origin": "https://survey.example",
        "question_text": "What is your current occupation?",
        "options": ["Teacher", "Engineer"],
        "required": True,
    }

    invalid_origin = client.post(
        "/api/v1/chrome-extension/proposals",
        headers=headers,
        json={**payload, "origin": "https://survey.example/path"},
    )
    assert invalid_origin.status_code == 422

    proposal = client.post(
        "/api/v1/chrome-extension/proposals",
        headers=headers,
        json=payload,
    )
    assert proposal.status_code == 200
    assert proposal.json()["support_status"] == "insufficient"

    event = client.post(
        "/api/v1/chrome-extension/audit",
        headers=headers,
        json={
            "profile_id": profile_id,
            "origin": payload["origin"],
            "action": "field_filled",
            "control_type": "text",
        },
    )
    assert event.status_code == 201
    assert event.json()["action"] == "field_filled"
    assert "What is your current occupation?" not in event.text


def test_extension_approval_does_not_save_proposal_as_a_profile_fact(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_id = _create_profile(client)
    db_factory = client.app.state.test_session
    with db_factory() as db:
        proposal = AnswerProposalRecord(
            profile_id=profile_id,
            question_text="What is your occupation?",
            answer_text="Architect",
            support_status="supported",
            confidence=0.9,
            status="pending",
            answer_format="text",
            question_analysis={
                "question_text": "What is your occupation?",
                "question_type": "free_text",
            },
            needs_user_input=False,
            needs_review=True,
        )
        db.add(proposal)
        db.commit()
        proposal_id = proposal.id

    approved = client.post(
        f"/api/v1/chrome-extension/proposals/{proposal_id}/approve",
        headers=_extension_headers(monkeypatch),
        json={"profile_id": profile_id, "origin": "https://survey.example"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    with db_factory() as db:
        assert db.query(ProfileFact).filter(ProfileFact.profile_id == profile_id).count() == 0


def test_cors_and_extension_token_configuration_are_strict() -> None:
    with pytest.raises(ValidationError):
        Settings(cors_allowed_origins="*")
    with pytest.raises(ValidationError):
        Settings(chrome_extension_api_token=SecretStr("short"))
    settings = Settings(
        cors_allowed_origins=f"http://localhost:4200,chrome-extension://{'a' * 32}",
    )
    assert settings.cors_allowed_origins == f"http://localhost:4200,chrome-extension://{'a' * 32}"
    with pytest.raises(ValidationError):
        Settings(cors_allowed_origins="http://user@localhost:4200")
