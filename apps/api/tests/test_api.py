"""Tests for the deterministic MemoryCue API vertical slice."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def seed(client: TestClient) -> None:
    response = client.post("/api/demo/seed")
    assert response.status_code == 200


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_recent_activity_query(client: TestClient) -> None:
    seed(client)
    response = client.post("/api/query", json={"question": "What was I doing?"})
    assert response.json() == {
        "answer": "You were preparing to leave.",
        "intent": "recent_activity",
        "source_ids": ["memory:4"],
    }


def test_keys_last_seen_query(client: TestClient) -> None:
    seed(client)
    response = client.post("/api/query", json={"question": "Where are my keys?"})
    body = response.json()
    assert body["answer"] == "I last saw your keys on the kitchen counter at 10:18 AM."
    assert body["intent"] == "object_location"
    assert body["source_ids"]


def test_person_lookup_query(client: TestClient) -> None:
    seed(client)
    response = client.post("/api/query", json={"question": "Who is Sarah?"})
    body = response.json()
    assert body["answer"] == "Sarah is your daughter."
    assert body["intent"] == "person_lookup"
    assert body["source_ids"]


def test_schedule_query(client: TestClient) -> None:
    seed(client)
    response = client.post("/api/query", json={"question": "What am I doing today?"})
    body = response.json()
    assert body["answer"] == "Sarah visits at 3:30 PM. Dinner is at 6:00 PM."
    assert body["intent"] == "schedule"
    assert len(body["source_ids"]) == 2


def test_unknown_query(client: TestClient) -> None:
    seed(client)
    response = client.post("/api/query", json={"question": "What is the weather?"})
    assert response.json() == {
        "answer": "I don't know that yet.",
        "intent": "unknown",
        "source_ids": [],
    }


def test_seed_can_be_run_twice_without_duplicate_demo_state(client: TestClient) -> None:
    first = client.post("/api/demo/seed")
    second = client.post("/api/demo/seed")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == {
        "status": "ok",
        "user_id": 1,
        "memory_count": 4,
        "observation_count": 1,
        "person_count": 1,
        "schedule_count": 2,
    }

    response = client.post("/api/query", json={"question": "Where are my keys?"})
    assert len(response.json()["source_ids"]) == 2
