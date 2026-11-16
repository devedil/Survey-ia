import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.ai.dependencies import get_memory_manager, get_model_router
from backend.app.ai.model_router import ModelConfigurationError, ModelRouter
from backend.app.answers.memory_manager import Evidence
from backend.app.answers.prompts import ANSWER_GENERATOR_PROMPT_VERSION
from backend.app.core.config import get_settings
from backend.app.core.database import Base, get_db
from backend.app.main import app
from backend.app.usage.models import ModelUsage


class FakeModelRouter:
    def __init__(self, answer_mode="supported"):
        self.answer_mode = answer_mode
        self.calls = []
        self.settings = get_settings()

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
        if call_budget:
            call_budget.consume()
        self.calls.append(operation)
        if operation == "question-analyzer-v1":
            return type(
                "Result",
                (),
                {
                    "data": {
                        "question_text": user_payload["question_text"],
                        "instructions": [],
                        "question_type": "single_choice" if user_payload["options"] else "free_text",
                        "options": user_payload["options"],
                        "required": user_payload["required"],
                        "max_length": user_payload["max_length"],
                        "language": "en",
                        "requests_personal_information": False,
                        "needs_additional_context": False,
                    }
                },
            )()

        if self.answer_mode == "invalid_citation":
            return type(
                "Result",
                (),
                {
                    "data": {
                        "suggested_answer": "Invented answer",
                        "support_status": "supported",
                        "confidence": 0.99,
                        "sources": [
                            {
                                "source_type": "profile_fact",
                                "source_id": "not-an-evidence-id",
                                "excerpt": "fabricated evidence",
                            }
                        ],
                        "needs_user_input": False,
                        "needs_review": False,
                        "review_reason": None,
                        "answer_format": "single_choice",
                    }
                },
            )()

        evidence = user_payload["evidence"][0]
        if self.answer_mode == "invalid_option":
            answer = "Maybe"
        else:
            answer = evidence["content"].partition(": ")[2]
        return type(
            "Result",
            (),
            {
                "data": {
                    "suggested_answer": answer,
                    "support_status": "supported",
                    "confidence": 0.9,
                    "sources": [
                        {
                            "source_type": evidence["source_type"],
                            "source_id": evidence["source_id"],
                            "excerpt": evidence["content"],
                        }
                    ],
                    "needs_user_input": False,
                    "needs_review": False,
                    "review_reason": None,
                    "answer_format": (
                        "single_choice" if user_payload["question"]["question_type"] == "single_choice" else "text"
                    ),
                }
            },
        )()


class FakeMemoryManager:
    def __init__(self, evidence):
        self.evidence = evidence

    def retrieve(self, db, profile_id, query, **kwargs):
        return self.evidence


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

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        test_client.app.state.test_session = test_session
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def _create_profile(client: TestClient) -> str:
    response = client.post("/api/v1/profiles", json={"name": "Test"})
    assert response.status_code == 201
    return response.json()["id"]


def _configure_ai(client: TestClient, router: FakeModelRouter, evidence: list[Evidence]) -> None:
    app.dependency_overrides[get_model_router] = lambda: router
    app.dependency_overrides[get_memory_manager] = lambda: FakeMemoryManager(evidence)


def test_answer_proposal_uses_verifiable_source_and_human_review(client: TestClient):
    profile_id = _create_profile(client)
    evidence = [Evidence("profile_fact", "fact-1", "city: Madrid", "city")]
    router = FakeModelRouter()
    _configure_ai(client, router, evidence)

    response = client.post(
        "/api/v1/answers/propose",
        json={"profile_id": profile_id, "question_text": "What is my city?"},
    )

    assert response.status_code == 200
    proposal = response.json()
    assert proposal["suggested_answer"] == "Madrid"
    assert proposal["support_status"] == "supported"
    assert proposal["sources"][0]["source_id"] == "fact-1"
    assert proposal["needs_review"] is True
    assert router.calls == ["question-analyzer-v1", ANSWER_GENERATOR_PROMPT_VERSION]


def test_unknown_evidence_abstains_without_calling_answer_generator(client: TestClient):
    profile_id = _create_profile(client)
    router = FakeModelRouter()
    _configure_ai(client, router, [])

    response = client.post(
        "/api/v1/answers/propose",
        json={"profile_id": profile_id, "question_text": "What was my childhood pet?"},
    )

    assert response.status_code == 200
    proposal = response.json()
    assert proposal["support_status"] == "insufficient"
    assert proposal["suggested_answer"] == ""
    assert proposal["needs_user_input"] is True
    assert router.calls == ["question-analyzer-v1"]


@pytest.mark.parametrize(
    ("mode", "expected_status"),
    [
        ("invalid_citation", "insufficient"),
        ("invalid_option", "insufficient"),
    ],
)
def test_invalid_citation_or_answer_format_abstains(client: TestClient, mode, expected_status):
    profile_id = _create_profile(client)
    router = FakeModelRouter(mode)
    evidence = [Evidence("profile_fact", "fact-1", "choice: Yes", "choice")]
    _configure_ai(client, router, evidence)

    response = client.post(
        "/api/v1/answers/propose",
        json={
            "profile_id": profile_id,
            "question_text": "Choose one",
            "options": ["Yes", "No"],
        },
    )
    assert response.status_code == 200
    assert response.json()["support_status"] == expected_status
    assert response.json()["suggested_answer"] == ""


def test_sensitive_question_stops_before_answer_generation(client: TestClient):
    profile_id = _create_profile(client)
    router = FakeModelRouter()
    _configure_ai(client, router, [Evidence("profile_fact", "fact-1", "salary: 100", "salary")])

    response = client.post(
        "/api/v1/answers/propose",
        json={"profile_id": profile_id, "question_text": "What is my salary?"},
    )
    assert response.status_code == 200
    assert response.json()["support_status"] == "sensitive"
    assert response.json()["suggested_answer"] == ""
    assert router.calls == []


def test_approval_does_not_save_proposal_without_explicit_opt_in(client: TestClient):
    profile_id = _create_profile(client)
    _configure_ai(
        client,
        FakeModelRouter(),
        [Evidence("profile_fact", "fact-1", "city: Madrid", "city")],
    )
    proposed = client.post(
        "/api/v1/answers/propose",
        json={"profile_id": profile_id, "question_text": "What is my city?"},
    ).json()

    approved = client.post(
        f"/api/v1/answers/{proposed['proposal_id']}/approve",
        params={"profile_id": profile_id},
        json={},
    )

    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert client.get("/api/v1/memory", params={"profile_id": profile_id}).json() == []
    feedback = client.get(
        f"/api/v1/answers/{proposed['proposal_id']}/history",
        params={"profile_id": profile_id},
    )
    assert feedback.status_code == 200
    assert feedback.json()[0]["approved_for_memory"] is False


def test_correction_can_be_reviewed_and_restored(client: TestClient):
    profile_id = _create_profile(client)
    _configure_ai(
        client,
        FakeModelRouter(),
        [Evidence("profile_fact", "fact-1", "city: Madrid", "city")],
    )
    proposed = client.post(
        "/api/v1/answers/propose",
        json={"profile_id": profile_id, "question_text": "What is my city?"},
    ).json()
    proposal_id = proposed["proposal_id"]
    corrected = client.post(
        f"/api/v1/answers/{proposal_id}/correct",
        params={"profile_id": profile_id},
        json={"correction": "Sevilla"},
    )
    assert corrected.status_code == 200
    assert corrected.json()["suggested_answer"] == "Sevilla"

    history = client.get(
        f"/api/v1/answers/{proposal_id}/history",
        params={"profile_id": profile_id},
    ).json()
    restored = client.post(
        f"/api/v1/answers/{proposal_id}/restore/{history[0]['id']}",
        params={"profile_id": profile_id},
    )

    assert restored.status_code == 200
    assert restored.json()["suggested_answer"] == "Madrid"
    assert client.get("/api/v1/memory", params={"profile_id": profile_id}).json() == []


def test_approved_fact_has_provenance_and_is_exported(client: TestClient):
    profile_id = _create_profile(client)
    _configure_ai(
        client,
        FakeModelRouter(),
        [Evidence("profile_fact", "fact-1", "city: Madrid", "city")],
    )
    proposed = client.post(
        "/api/v1/answers/propose",
        json={"profile_id": profile_id, "question_text": "What is my city?"},
    ).json()

    approved = client.post(
        f"/api/v1/answers/{proposed['proposal_id']}/approve",
        params={"profile_id": profile_id},
        json={
            "save_as_fact": True,
            "field_name": "city",
            "consent_to_retrieve": True,
        },
    )

    assert approved.status_code == 200
    fact_id = approved.json()["created_fact_id"]
    facts = client.get("/api/v1/memory", params={"profile_id": profile_id}).json()
    assert len(facts) == 1
    assert facts[0]["id"] == fact_id
    assert facts[0]["source_type"] == "answer_proposal"
    assert facts[0]["source_id"] == proposed["proposal_id"]
    assert facts[0]["status"] == "verified"

    export = client.get(
        "/api/v1/memory/export",
        params={"profile_id": profile_id},
    )
    assert export.status_code == 200
    assert export.json()["facts"][0]["id"] == fact_id
    assert export.json()["proposals"][0]["id"] == proposed["proposal_id"]


def test_unverified_facts_are_not_searchable_and_expired_facts_are_marked(client: TestClient):
    from datetime import datetime, timedelta, timezone

    profile_id = _create_profile(client)
    pending = client.post(
        f"/api/v1/profiles/{profile_id}/facts",
        json={"field_name": "city", "value": "Madrid", "is_verified": False},
    )
    assert pending.status_code == 201
    assert pending.json()["status"] == "pending"

    expired = client.post(
        f"/api/v1/profiles/{profile_id}/facts",
        json={
            "field_name": "former_city",
            "value": "Toledo",
            "valid_until": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        },
    )
    assert expired.status_code == 201
    expired_fact_id = expired.json()["id"]
    search = client.post(
        "/api/v1/memory/search",
        json={"profile_id": profile_id, "query": "city"},
    )
    assert search.status_code == 200
    assert search.json() == []

    memory = client.get(
        "/api/v1/memory",
        params={"profile_id": profile_id, "include_expired": True},
    ).json()
    expired_fact = next(fact for fact in memory if fact["id"] == expired_fact_id)
    assert expired_fact["status"] == "expired"


def test_contradictory_profile_facts_are_reported_without_generation(client: TestClient):
    profile_id = _create_profile(client)
    router = FakeModelRouter()
    evidence = [
        Evidence("profile_fact", "fact-1", "age: 30", "age"),
        Evidence("profile_fact", "fact-2", "age: 31", "age"),
    ]
    _configure_ai(client, router, evidence)

    response = client.post(
        "/api/v1/answers/propose",
        json={"profile_id": profile_id, "question_text": "What is my age?"},
    )

    assert response.status_code == 200
    proposal = response.json()
    assert proposal["support_status"] == "contradictory"
    assert proposal["suggested_answer"] == ""
    assert {source["source_id"] for source in proposal["sources"]} == {"fact-1", "fact-2"}
    assert router.calls == ["question-analyzer-v1"]


def test_model_call_limit_causes_safe_abstention(client: TestClient, monkeypatch):
    profile_id = _create_profile(client)
    router = FakeModelRouter()
    _configure_ai(client, router, [Evidence("profile_fact", "fact-1", "city: Madrid", "city")])
    monkeypatch.setattr(get_settings(), "max_calls_per_question", 1)

    response = client.post(
        "/api/v1/answers/propose",
        json={"profile_id": profile_id, "question_text": "What is my city?"},
    )

    assert response.status_code == 200
    assert response.json()["support_status"] == "insufficient"
    assert response.json()["suggested_answer"] == ""
    assert router.calls == ["question-analyzer-v1"]


def test_model_router_reports_missing_key_without_losing_usage_record(client: TestClient, monkeypatch):
    profile_id = _create_profile(client)
    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", "replace_me")
    monkeypatch.setattr(settings, "openai_default_model", "test-model")

    with client.app.state.test_session() as db:
        with pytest.raises(ModelConfigurationError, match="OPENAI_API_KEY"):
            ModelRouter().complete_json(
                db,
                profile_id=profile_id,
                operation="test",
                system_prompt="test prompt",
                user_payload={"question": "test"},
            )
        usage = db.query(ModelUsage).one()
        usage_result = (usage.status, usage.error_code, usage.input_tokens)

    assert usage_result == ("failed", "configuration_error", None)


def test_model_router_logs_tokens_and_configured_price(client: TestClient, monkeypatch):
    from types import SimpleNamespace

    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
                model="test-model",
                usage=SimpleNamespace(
                    prompt_tokens=120,
                    completion_tokens=30,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=20),
                ),
            )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    router = ModelRouter(client=fake_client)
    monkeypatch.setattr(get_settings(), "openai_default_model", "test-model")
    monkeypatch.setattr(
        get_settings(),
        "openai_pricing_catalog",
        '{"test-model":{"version":"catalog-2026-01","input_usd_per_million":2,"output_usd_per_million":4}}',
    )
    profile_id = _create_profile(client)

    with client.app.state.test_session() as db:
        result = router.complete_json(
            db,
            profile_id=profile_id,
            operation="test",
            system_prompt="test prompt",
            user_payload={"question": "test"},
        )
        usage = db.query(ModelUsage).one()
        usage_result = (
            usage.status,
            usage.input_tokens,
            usage.output_tokens,
            usage.cached_input_tokens,
            usage.cost_usd,
            usage.pricing_version,
            usage.cost_is_estimated,
        )

    assert result.data == {"ok": True}
    assert usage_result == ("succeeded", 120, 30, 20, pytest.approx(0.00036), "catalog-2026-01", False)
