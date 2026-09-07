"""Tests for the deterministic MemoryCue API vertical slice."""

from collections.abc import Generator
from datetime import datetime
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:
    media_directory = tmp_path / "media"
    monkeypatch.setenv("MEDIA_DIR", str(media_directory))
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


def upload_memory(
    client: TestClient,
    *,
    timestamp: str,
    location: str,
    description: str,
    object_name: str | None = None,
    filename: str = "memory.jpg",
):
    data = {
        "timestamp": timestamp,
        "location": location,
        "description": description,
    }
    if object_name is not None:
        data["object_name"] = object_name
    return client.post(
        "/api/memories",
        files={"image": (filename, b"fake-image-content", "image/jpeg")},
        data=data,
    )


def timestamp_at(hour: int = 10, minute: int = 42) -> str:
    return datetime.now().replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    ).isoformat(timespec="seconds")


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


def test_create_uploaded_memory(client: TestClient) -> None:
    seed(client)
    timestamp = timestamp_at()
    response = upload_memory(
        client,
        timestamp=timestamp,
        location="Kitchen counter",
        description="I left my keys on the kitchen counter.",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["timestamp"] == timestamp
    assert body["location"] == "Kitchen counter"
    assert body["activity"] is None
    assert body["object_observation_id"] is None
    assert body["image_url"].startswith("/api/media/")

    stored_filename = body["image_url"].rsplit("/", 1)[-1]
    stored_path = Path(os.environ["MEDIA_DIR"]) / stored_filename
    assert stored_path.is_file()
    media_response = client.get(body["image_url"])
    assert media_response.status_code == 200
    assert media_response.content == b"fake-image-content"


def test_create_memory_with_object_observation(client: TestClient) -> None:
    seed(client)
    response = upload_memory(
        client,
        timestamp=timestamp_at(),
        location="Kitchen counter",
        description="I left my keys on the kitchen counter.",
        object_name="Keys",
    )

    assert response.status_code == 201
    assert response.json()["object_observation_id"] > 0
    query_response = client.post("/api/query", json={"question": "Where are my keys?"})
    assert query_response.json()["answer"] == (
        "I last saw your keys on the Kitchen counter at 10:42 AM."
    )


def test_latest_uploaded_object_overrides_seeded_last_seen(client: TestClient) -> None:
    seed(client)
    newer_timestamp = timestamp_at()
    response = upload_memory(
        client,
        timestamp=newer_timestamp,
        location="bedroom desk",
        description="I left my keys on the bedroom desk.",
        object_name="keys",
    )
    assert response.status_code == 201

    query_response = client.post("/api/query", json={"question": "Where are my keys?"})
    assert query_response.json()["answer"] == (
        "I last saw your keys on the bedroom desk at 10:42 AM."
    )


def test_reject_unsupported_file_type(client: TestClient) -> None:
    response = upload_memory(
        client,
        timestamp=timestamp_at(),
        location="Kitchen counter",
        description="An unsupported file.",
        filename="memory.gif",
    )
    assert response.status_code == 400
    assert "Unsupported image type" in response.json()["detail"]


def test_reject_missing_required_fields(client: TestClient) -> None:
    missing_form_fields = client.post(
        "/api/memories",
        files={"image": ("memory.jpg", b"fake-image-content", "image/jpeg")},
    )
    assert missing_form_fields.status_code == 422
    locations = {entry["loc"][-1] for entry in missing_form_fields.json()["detail"]}
    assert {"timestamp", "location", "description"}.issubset(locations)

    missing_image = client.post(
        "/api/memories",
        data={
            "timestamp": "2026-09-07T10:42:00",
            "location": "Kitchen counter",
            "description": "No image was supplied.",
        },
    )
    assert missing_image.status_code == 422


def test_media_path_traversal_is_blocked(client: TestClient) -> None:
    response = client.get("/api/media/..%5Csecret.txt")
    assert response.status_code == 404


def test_memory_listing_is_newest_first(client: TestClient) -> None:
    seed(client)
    upload_memory(
        client,
        timestamp=timestamp_at(),
        location="Bedroom desk",
        description="I left my keys on the bedroom desk.",
        object_name="keys",
    )

    response = client.get("/api/memories")
    assert response.status_code == 200
    memories = response.json()
    assert len(memories) == 5
    assert memories[0]["location"] == "Bedroom desk"
    assert memories[0]["description"] == "I left my keys on the bedroom desk."
    assert memories[0]["image_url"].startswith("/api/media/")
