import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base, get_db
from backend.app.main import app


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
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def test_profile_and_fact_crud_flow(client: TestClient) -> None:
    response = client.post("/api/v1/profiles", json={"name": "Ana", "email": "ana@example.com"})
    assert response.status_code == 201
    profile = response.json()
    profile_id = profile["id"]
    assert profile["name"] == "Ana"

    response = client.post(
        f"/api/v1/profiles/{profile_id}/facts",
        json={
            "field_name": "city",
            "value": "Madrid",
            "source": "user",
            "confidence": 0.99,
            "is_verified": True,
            "notes": "Confirmado por el usuario",
        },
    )
    assert response.status_code == 201
    fact = response.json()
    fact_id = fact["id"]
    assert fact["field_name"] == "city"

    response = client.get(f"/api/v1/profiles/{profile_id}/facts")
    assert response.status_code == 200
    facts = response.json()
    assert len(facts) == 1
    assert facts[0]["id"] == fact_id

    response = client.patch(
        f"/api/v1/profiles/{profile_id}/facts/{fact_id}",
        json={"value": "Sevilla", "confidence": 0.8},
    )
    assert response.status_code == 200
    updated_fact = response.json()
    assert updated_fact["value"] == "Sevilla"
    assert updated_fact["confidence"] == 0.8

    response = client.get(f"/api/v1/profiles/{profile_id}/facts/{fact_id}/history")
    assert response.status_code == 200
    history = response.json()
    assert any(revision["change_type"] == "updated" for revision in history)
    created_revision = next(
        revision for revision in history if revision["change_type"] == "created"
    )

    response = client.post(
        f"/api/v1/profiles/{profile_id}/facts/{fact_id}/history/{created_revision['id']}/restore"
    )
    assert response.status_code == 200
    assert response.json()["value"] == "Madrid"

    response = client.get(f"/api/v1/profiles/{profile_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Ana"

    response = client.delete(f"/api/v1/profiles/{profile_id}")
    assert response.status_code == 204

    response = client.get(f"/api/v1/profiles/{profile_id}")
    assert response.status_code == 404


def test_memory_detects_duplicates_and_deletes_facts(client: TestClient) -> None:
    profile_id = client.post("/api/v1/profiles", json={"name": "Ana"}).json()["id"]
    first = client.post(
        f"/api/v1/profiles/{profile_id}/facts",
        json={"field_name": "city", "value": "Madrid"},
    ).json()
    second = client.post(
        f"/api/v1/profiles/{profile_id}/facts",
        json={"field_name": "CITY", "value": "madrid"},
    ).json()

    duplicates = client.get(
        "/api/v1/memory/duplicates",
        params={"profile_id": profile_id},
    )
    assert duplicates.status_code == 200
    assert len(duplicates.json()) == 1
    assert set(duplicates.json()[0]["fact_ids"]) == {first["id"], second["id"]}

    deleted = client.delete(
        f"/api/v1/memory/{first['id']}",
        params={"profile_id": profile_id},
    )
    assert deleted.status_code == 204
    assert client.get(
        "/api/v1/memory/duplicates",
        params={"profile_id": profile_id},
    ).json() == []
