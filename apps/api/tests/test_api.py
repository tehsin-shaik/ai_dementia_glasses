"""Tests for the deterministic MemoryCue API vertical slice."""

from collections.abc import Generator
from datetime import datetime
import os
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, create_database_engine, get_db
from app.identity import USER_ID_HEADER
from app.main import app
from app.media_storage import MAX_UPLOAD_BYTES, safe_media_path
from app.vision import VisionAnalysis
from app.vision import provider as vision_provider
from app.vision.provider import VisionProviderError


@pytest.fixture
def client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:
    media_directory = tmp_path / "media"
    monkeypatch.setenv("MEDIA_DIR", str(media_directory))
    monkeypatch.delenv("VISION_PROVIDER", raising=False)
    monkeypatch.delenv("VISION_MODEL", raising=False)
    monkeypatch.delenv("VISION_API_KEY", raising=False)
    engine = create_database_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
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
    with TestClient(app, headers={USER_ID_HEADER: "1"}) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def seed(client: TestClient) -> None:
    response = client.post("/api/demo/seed")
    assert response.status_code == 200


def user_headers(user_id: int) -> dict[str, str]:
    return {USER_ID_HEADER: str(user_id)}


def upload_memory(
    client: TestClient,
    *,
    timestamp: str,
    location: str,
    description: str,
    activity: str | None = None,
    object_name: str | None = None,
    filename: str = "memory.jpg",
    user_id: int = 1,
):
    data = {
        "timestamp": timestamp,
        "location": location,
        "description": description,
    }
    if object_name is not None:
        data["object_name"] = object_name
    if activity is not None:
        data["activity"] = activity
    return client.post(
        "/api/memories",
        files={"image": (filename, b"fake-image-content", "image/jpeg")},
        data=data,
        headers=user_headers(user_id),
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


def test_sqlite_foreign_keys_are_enabled(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'integrity.db'}")
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    finally:
        engine.dispose()


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
        "user_ids": [1, 2],
        "user_count": 2,
        "memory_count": 8,
        "observation_count": 2,
        "person_count": 2,
        "schedule_count": 4,
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


def test_timezone_aware_timestamp_uses_backend_local_time(client: TestClient) -> None:
    seed(client)
    aware_timestamp = datetime.now().astimezone().replace(second=0, microsecond=0)
    response = upload_memory(
        client,
        timestamp=aware_timestamp.isoformat(),
        location="Kitchen counter",
        description="A timestamp with an explicit timezone.",
    )

    assert response.status_code == 201
    assert response.json()["timestamp"] == aware_timestamp.replace(tzinfo=None).isoformat()


def test_failed_memory_commit_removes_uploaded_image(client: TestClient, monkeypatch) -> None:
    seed(client)
    def fail_commit(_session) -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(Session, "commit", fail_commit)
    with TestClient(app, raise_server_exceptions=False) as failing_client:
        response = upload_memory(
            failing_client,
            timestamp=timestamp_at(),
            location="Kitchen counter",
            description="The database write will fail.",
        )

    assert response.status_code == 500
    media_directory = Path(os.environ["MEDIA_DIR"])
    assert not media_directory.exists() or not list(media_directory.iterdir())


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
    seed(client)
    response = upload_memory(
        client,
        timestamp=timestamp_at(),
        location="Kitchen counter",
        description="An unsupported file.",
        filename="memory.gif",
    )
    assert response.status_code == 400
    assert "Unsupported image type" in response.json()["detail"]


def test_reject_mismatched_image_content_type(client: TestClient) -> None:
    seed(client)
    response = client.post(
        "/api/memories",
        files={"image": ("memory.png", b"fake-image-content", "image/jpeg")},
        data={
            "timestamp": timestamp_at(),
            "location": "Kitchen counter",
            "description": "The image type is intentionally mismatched.",
        },
    )
    assert response.status_code == 400
    assert "content type" in response.json()["detail"]


def test_reject_oversized_image(client: TestClient) -> None:
    seed(client)
    response = client.post(
        "/api/memories",
        files={"image": ("memory.jpg", b"x" * (MAX_UPLOAD_BYTES + 1), "image/jpeg")},
        data={
            "timestamp": timestamp_at(),
            "location": "Kitchen counter",
            "description": "The image is intentionally oversized.",
        },
    )
    assert response.status_code == 413


def test_reject_memory_field_overflow(client: TestClient) -> None:
    seed(client)
    response = upload_memory(
        client,
        timestamp=timestamp_at(),
        location="k" * 121,
        description="A valid description.",
    )
    assert response.status_code == 422
    assert "Location cannot exceed" in response.json()["detail"]


def test_reject_missing_required_fields(client: TestClient) -> None:
    seed(client)
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


@pytest.mark.parametrize(
    "filename",
    [
        "../secret.jpg",
        "../../secret.jpg",
        "..%2Fsecret.jpg",
        "..\\secret.jpg",
        "C:/secret.jpg",
        "C:\\secret.jpg",
        "/etc/passwd",
        "notes.txt",
    ],
)
def test_media_path_traversal_is_blocked(client: TestClient, tmp_path, monkeypatch, filename: str) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    with pytest.raises(HTTPException) as error:
        safe_media_path(filename)
    assert error.value.status_code == 404


def test_media_path_traversal_is_blocked_by_route(client: TestClient) -> None:
    seed(client)
    response = client.get("/api/media/..%5Csecret.txt")
    assert response.status_code == 404


def test_unsupported_media_file_is_not_served(client: TestClient, tmp_path, monkeypatch) -> None:
    seed(client)
    media_directory = tmp_path / "media"
    media_directory.mkdir()
    (media_directory / "notes.txt").write_text("not an image", encoding="utf-8")
    monkeypatch.setenv("MEDIA_DIR", str(media_directory))

    response = client.get("/api/media/notes.txt")

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


def test_vision_analysis_returns_normalized_result(client: TestClient, monkeypatch) -> None:
    seed(client)
    memories_before = client.get("/api/memories").json()
    class StubVisionAnalyzer:
        async def analyze_image(self, image_bytes, filename, context=None):
            assert image_bytes == b"fake-image-content"
            assert filename == "memory.jpg"
            assert context == "Focus on useful everyday details."
            return VisionAnalysis(
                description="A set of keys is resting on a kitchen counter.",
                location="Kitchen counter",
                activity=None,
                objects=[{"name": "keys", "location": "Kitchen counter", "confidence": 0.98}],
            )

    monkeypatch.setattr(vision_provider, "get_vision_analyzer", lambda: StubVisionAnalyzer())
    response = client.post(
        "/api/vision/analyze",
        files={"image": ("memory.jpg", b"fake-image-content", "image/jpeg")},
        data={"context": "Focus on useful everyday details."},
    )

    assert response.status_code == 200
    assert response.json() == {
        "description": "A set of keys is resting on a kitchen counter.",
        "location": "Kitchen counter",
        "activity": None,
        "objects": [
            {"name": "keys", "location": "Kitchen counter", "confidence": 0.98}
        ],
    }
    assert client.get("/api/memories").json() == memories_before


def test_vision_analysis_requires_image(client: TestClient) -> None:
    seed(client)
    response = client.post("/api/vision/analyze")
    assert response.status_code == 422


def test_vision_analysis_rejects_unsupported_file_type(client: TestClient) -> None:
    seed(client)
    response = client.post(
        "/api/vision/analyze",
        files={"image": ("memory.gif", b"fake-image-content", "image/gif")},
    )
    assert response.status_code == 400
    assert "Unsupported image type" in response.json()["detail"]


def test_vision_analysis_handles_provider_not_configured(client: TestClient) -> None:
    seed(client)
    response = client.post(
        "/api/vision/analyze",
        files={"image": ("memory.jpg", b"fake-image-content", "image/jpeg")},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Vision analysis is not configured."}


def test_vision_analysis_handles_invalid_provider_response(client: TestClient, monkeypatch) -> None:
    seed(client)
    class InvalidVisionAnalyzer:
        async def analyze_image(self, image_bytes, filename, context=None):
            return {"description": "This has an unexpected shape.", "unexpected": True}

    monkeypatch.setattr(vision_provider, "get_vision_analyzer", lambda: InvalidVisionAnalyzer())
    response = client.post(
        "/api/vision/analyze",
        files={"image": ("memory.jpg", b"fake-image-content", "image/jpeg")},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "The image could not be analyzed."}


def test_vision_analysis_handles_provider_failure(client: TestClient, monkeypatch) -> None:
    seed(client)
    class FailingVisionAnalyzer:
        async def analyze_image(self, image_bytes, filename, context=None):
            raise VisionProviderError("provider failed")

    monkeypatch.setattr(vision_provider, "get_vision_analyzer", lambda: FailingVisionAnalyzer())
    response = client.post(
        "/api/vision/analyze",
        files={"image": ("memory.jpg", b"fake-image-content", "image/jpeg")},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "The image could not be analyzed."}


def test_manual_memory_creation_still_works_without_ai(client: TestClient) -> None:
    seed(client)
    response = upload_memory(
        client,
        timestamp=timestamp_at(11, 5),
        location="Living room",
        description="A book is on the coffee table.",
    )
    assert response.status_code == 201
    assert response.json()["description"] == "A book is on the coffee table."


def test_recent_activity_uses_latest_non_null_activity(client: TestClient) -> None:
    seed(client)
    activity_response = upload_memory(
        client,
        timestamp=timestamp_at(10, 30),
        location="Living room",
        description="I was reading in the living room.",
        activity="reading in the living room",
    )
    assert activity_response.status_code == 201
    newer_without_activity = upload_memory(
        client,
        timestamp=timestamp_at(10, 40),
        location="Hallway",
        description="I was standing in the hallway.",
    )
    assert newer_without_activity.status_code == 201

    response = client.post("/api/query", json={"question": "What was I doing?"})
    assert response.json()["answer"] == "You were reading in the living room."


def test_personal_endpoints_require_identity(client: TestClient) -> None:
    seed(client)
    with TestClient(app) as anonymous_client:
        health_response = anonymous_client.get("/api/health")
        seed_response = anonymous_client.post("/api/demo/seed")
        query_response = anonymous_client.post(
            "/api/query",
            json={"question": "Where are my keys?"},
        )
        memories_response = anonymous_client.get("/api/memories")
        create_response = anonymous_client.post(
            "/api/memories",
            files={"image": ("memory.jpg", b"fake-image-content", "image/jpeg")},
            data={
                "timestamp": timestamp_at(),
                "location": "Kitchen counter",
                "description": "No identity should be accepted.",
            },
        )
        vision_response = anonymous_client.post(
            "/api/vision/analyze",
            files={"image": ("memory.jpg", b"fake-image-content", "image/jpeg")},
        )
        media_response = anonymous_client.get("/api/media/missing.jpg")

    assert health_response.status_code == 200
    assert seed_response.status_code == 200
    assert query_response.status_code == 401
    assert query_response.json() == {"detail": "User identity is required."}
    assert memories_response.status_code == 401
    assert memories_response.json() == {"detail": "User identity is required."}
    assert create_response.status_code == 401
    assert create_response.json() == {"detail": "User identity is required."}
    assert vision_response.status_code == 401
    assert vision_response.json() == {"detail": "User identity is required."}
    assert media_response.status_code == 401
    assert media_response.json() == {"detail": "User identity is required."}


def test_unknown_identity_is_rejected_consistently(client: TestClient) -> None:
    seed(client)
    headers = user_headers(999)
    query_response = client.post(
        "/api/query",
        json={"question": "Where are my keys?"},
        headers=headers,
    )
    memories_response = client.get("/api/memories", headers=headers)

    assert query_response.status_code == 404
    assert query_response.json() == {"detail": "User not found."}
    assert memories_response.status_code == 404
    assert memories_response.json() == {"detail": "User not found."}


def test_malformed_identity_is_rejected_as_unknown_user(client: TestClient) -> None:
    seed(client)
    response = client.post(
        "/api/query",
        headers={USER_ID_HEADER: "not-a-user"},
        json={"question": "Where are my keys?"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found."}


def test_queries_are_scoped_to_selected_user(client: TestClient) -> None:
    seed(client)

    alex_keys = client.post(
        "/api/query",
        json={"question": "Where are my keys?"},
        headers=user_headers(1),
    ).json()
    jordan_keys = client.post(
        "/api/query",
        json={"question": "Where are my keys?"},
        headers=user_headers(2),
    ).json()
    alex_person = client.post(
        "/api/query",
        json={"question": "Who is Sarah?"},
        headers=user_headers(1),
    ).json()
    jordan_person = client.post(
        "/api/query",
        json={"question": "Who is Sarah?"},
        headers=user_headers(2),
    ).json()
    alex_schedule = client.post(
        "/api/query",
        json={"question": "What am I doing today?"},
        headers=user_headers(1),
    ).json()
    jordan_schedule = client.post(
        "/api/query",
        json={"question": "What am I doing today?"},
        headers=user_headers(2),
    ).json()

    assert alex_keys["answer"] == "I last saw your keys on the kitchen counter at 10:18 AM."
    assert jordan_keys["answer"] == "I last saw your keys on the bedroom desk at 10:24 AM."
    assert alex_keys["source_ids"] != jordan_keys["source_ids"]
    assert alex_person["answer"] == "Sarah is your daughter."
    assert jordan_person["answer"] == "Sarah is your neighbor."
    assert alex_person["source_ids"] != jordan_person["source_ids"]
    assert alex_schedule["answer"] == "Sarah visits at 3:30 PM. Dinner is at 6:00 PM."
    assert jordan_schedule["answer"] == "Michael calls at 4:00 PM. Dinner is at 6:30 PM."
    assert alex_schedule["source_ids"] != jordan_schedule["source_ids"]


def test_memory_listing_and_creation_are_scoped_to_selected_user(client: TestClient) -> None:
    seed(client)
    alex_response = upload_memory(
        client,
        timestamp=timestamp_at(11, 0),
        location="Alex desk",
        description="Alex added this memory.",
        user_id=1,
    )
    jordan_response = upload_memory(
        client,
        timestamp=timestamp_at(11, 1),
        location="Jordan desk",
        description="Jordan added this memory.",
        user_id=2,
    )
    assert alex_response.status_code == 201
    assert jordan_response.status_code == 201

    alex_memories = client.get("/api/memories", headers=user_headers(1)).json()
    jordan_memories = client.get("/api/memories", headers=user_headers(2)).json()
    alex_descriptions = {memory["description"] for memory in alex_memories}
    jordan_descriptions = {memory["description"] for memory in jordan_memories}

    assert "Alex added this memory." in alex_descriptions
    assert "Jordan added this memory." not in alex_descriptions
    assert "Jordan added this memory." in jordan_descriptions
    assert "Alex added this memory." not in jordan_descriptions


def test_memory_creation_ignores_client_user_id_payload(client: TestClient) -> None:
    seed(client)
    response = client.post(
        "/api/memories",
        headers=user_headers(1),
        files={"image": ("memory.jpg", b"alex-image", "image/jpeg")},
        data={
            "timestamp": timestamp_at(11, 2),
            "location": "Alex kitchen",
            "description": "The selected user owns this memory.",
            "user_id": "2",
        },
    )
    assert response.status_code == 201

    alex_descriptions = {
        memory["description"]
        for memory in client.get("/api/memories", headers=user_headers(1)).json()
    }
    jordan_descriptions = {
        memory["description"]
        for memory in client.get("/api/memories", headers=user_headers(2)).json()
    }
    assert "The selected user owns this memory." in alex_descriptions
    assert "The selected user owns this memory." not in jordan_descriptions


def test_object_observations_are_scoped_to_selected_user(client: TestClient) -> None:
    seed(client)
    alex_response = upload_memory(
        client,
        timestamp=timestamp_at(11, 3),
        location="Alex table",
        description="Alex saw keys on the table.",
        object_name="keys",
        user_id=1,
    )
    jordan_response = upload_memory(
        client,
        timestamp=timestamp_at(11, 4),
        location="Jordan shelf",
        description="Jordan saw keys on the shelf.",
        object_name="keys",
        user_id=2,
    )
    assert alex_response.status_code == 201
    assert jordan_response.status_code == 201

    alex_answer = client.post(
        "/api/query",
        json={"question": "Where are my keys?"},
        headers=user_headers(1),
    ).json()["answer"]
    jordan_answer = client.post(
        "/api/query",
        json={"question": "Where are my keys?"},
        headers=user_headers(2),
    ).json()["answer"]
    assert alex_answer == "I last saw your keys on the Alex table at 11:03 AM."
    assert jordan_answer == "I last saw your keys on the Jordan shelf at 11:04 AM."


def test_media_is_only_available_to_its_owner(client: TestClient) -> None:
    seed(client)
    response = upload_memory(
        client,
        timestamp=timestamp_at(11, 5),
        location="Alex kitchen",
        description="An image belonging to Alex.",
        user_id=1,
    )
    assert response.status_code == 201
    image_url = response.json()["image_url"]

    unauthorized = client.get(image_url, headers=user_headers(2))
    authorized = client.get(image_url, headers=user_headers(1))
    assert unauthorized.status_code == 404
    assert unauthorized.json() == {"detail": "Media file not found."}
    assert authorized.status_code == 200
    assert authorized.content == b"fake-image-content"
