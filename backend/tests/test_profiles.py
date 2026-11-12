import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(__file__).resolve().parents[1] / "test_ai_survey_assistant.db")

from fastapi.testclient import TestClient

from backend.app.core.database import Base, engine
from backend.app.main import app

Base.metadata.create_all(bind=engine)
client = TestClient(app)


def test_profile_and_fact_crud_flow() -> None:
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

    response = client.get(f"/api/v1/profiles/{profile_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Ana"

    response = client.delete(f"/api/v1/profiles/{profile_id}")
    assert response.status_code == 204

    response = client.get(f"/api/v1/profiles/{profile_id}")
    assert response.status_code == 404
