"""Tests for the deterministic MemoryCue API vertical slice."""

import asyncio
from collections.abc import Generator
from datetime import datetime, timedelta
import json
import os
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, create_database_engine, get_db, normalize_database_url
from app.authorization import CAREGIVER_ID_HEADER
from app.cues import routes as cue_routes
from app.cues import service as cue_service
from app.face import provider as face_provider
from app.face.base import MultipleFacesFoundError, NoFaceFoundError
from app.identity import USER_ID_HEADER
from app.main import app
from app.media_storage import MAX_UPLOAD_BYTES, safe_media_path
from app.models import User
from app.runtime import allowed_origins, seed_if_empty
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


def clear_schedule(client: TestClient, patient_id: int) -> None:
    response = client.get(
        f"/api/caregiver/patients/{patient_id}/schedule",
        headers=caregiver_headers(patient_id),
    )
    assert response.status_code == 200
    for item in response.json():
        deleted = client.delete(
            f"/api/caregiver/patients/{patient_id}/schedule/{item['id']}",
            headers=caregiver_headers(patient_id),
        )
        assert deleted.status_code == 204


def user_headers(user_id: int) -> dict[str, str]:
    return {USER_ID_HEADER: str(user_id)}


def caregiver_headers(caregiver_id: int) -> dict[str, str]:
    return {CAREGIVER_ID_HEADER: str(caregiver_id)}


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


def timestamp_in(minutes: int) -> str:
    return (datetime.now() + timedelta(minutes=minutes)).replace(second=0, microsecond=0).isoformat(timespec="seconds")


class StubFaceRecognizer:
    """Small deterministic stand-in so API tests do not need real face inference."""

    EMBEDDINGS = {
        b"sarah-reference": [1.0, 0.0],
        b"sarah-camera": [1.0, 0.0],
        b"emma-reference": [0.0, 1.0],
        b"emma-camera": [0.0, 1.0],
        b"jordan-reference": [0.0, 1.0],
        b"weak-camera": [0.4, 0.0],
        b"ambiguous-camera": [0.82, 0.78],
    }

    def extract_embedding(self, image_bytes: bytes) -> list[float]:
        if image_bytes == b"no-face":
            raise NoFaceFoundError("No usable face was found.")
        if image_bytes == b"multiple-faces":
            raise MultipleFacesFoundError("Multiple faces were found.")
        return self.EMBEDDINGS.get(image_bytes, [0.0, 0.0])

    def compare(self, embedding_a: list[float], embedding_b: list[float]) -> float:
        if embedding_a == [0.82, 0.78]:
            if embedding_b == [1.0, 0.0]:
                return 0.82
            if embedding_b == [0.0, 1.0]:
                return 0.78
        distance = sum((left - right) ** 2 for left, right in zip(embedding_a, embedding_b)) ** 0.5
        return max(0.0, min(1.0, 1.0 - distance))


def upload_face(
    client: TestClient,
    *,
    patient_id: int,
    person_id: int,
    caregiver_id: int,
    image_bytes: bytes,
):
    return client.post(
        f"/api/caregiver/patients/{patient_id}/people/{person_id}/face",
        files={"image": ("face.jpg", image_bytes, "image/jpeg")},
        headers=caregiver_headers(caregiver_id),
    )


def recognize_face(client: TestClient, *, user_id: int, image_bytes: bytes):
    return client.post(
        "/api/face/recognize",
        files={"image": ("camera.jpg", image_bytes, "image/jpeg")},
        headers=user_headers(user_id),
    )


def test_face_enrollment_requires_manage_people(client: TestClient, monkeypatch) -> None:
    seed(client)
    monkeypatch.setattr(face_provider, "get_face_recognizer", lambda: StubFaceRecognizer())
    sarah = client.get("/api/caregiver/patients/1/people", headers=caregiver_headers(1)).json()[0]

    response = upload_face(
        client,
        patient_id=1,
        person_id=sarah["id"],
        caregiver_id=3,
        image_bytes=b"sarah-reference",
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Caregiver permission required."}


def test_face_enrollment_rejects_no_face(client: TestClient, monkeypatch) -> None:
    seed(client)
    monkeypatch.setattr(face_provider, "get_face_recognizer", lambda: StubFaceRecognizer())
    sarah = client.get("/api/caregiver/patients/1/people", headers=caregiver_headers(1)).json()[0]

    response = upload_face(
        client,
        patient_id=1,
        person_id=sarah["id"],
        caregiver_id=1,
        image_bytes=b"no-face",
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "No usable face was found."}


def test_face_enrollment_rejects_multiple_faces(client: TestClient, monkeypatch) -> None:
    seed(client)
    monkeypatch.setattr(face_provider, "get_face_recognizer", lambda: StubFaceRecognizer())
    sarah = client.get("/api/caregiver/patients/1/people", headers=caregiver_headers(1)).json()[0]

    response = upload_face(
        client,
        patient_id=1,
        person_id=sarah["id"],
        caregiver_id=1,
        image_bytes=b"multiple-faces",
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Multiple faces were found. Please upload a photo containing one person."
    }


def test_face_recognition_matches_enrolled_person(client: TestClient, monkeypatch) -> None:
    seed(client)
    monkeypatch.setattr(face_provider, "get_face_recognizer", lambda: StubFaceRecognizer())
    sarah = client.get("/api/caregiver/patients/1/people", headers=caregiver_headers(1)).json()[0]
    enrollment = upload_face(
        client,
        patient_id=1,
        person_id=sarah["id"],
        caregiver_id=1,
        image_bytes=b"sarah-reference",
    )

    response = recognize_face(client, user_id=1, image_bytes=b"sarah-camera")

    assert enrollment.status_code == 200
    assert response.status_code == 200
    assert response.json() == {
        "recognized": True,
        "person_id": sarah["id"],
        "name": "Sarah",
        "relationship": "Daughter",
        "confidence": 1.0,
    }


def test_face_recognition_returns_unknown_below_threshold(client: TestClient, monkeypatch) -> None:
    seed(client)
    monkeypatch.setattr(face_provider, "get_face_recognizer", lambda: StubFaceRecognizer())
    monkeypatch.setenv("FACE_MATCH_THRESHOLD", "0.65")
    sarah = client.get("/api/caregiver/patients/1/people", headers=caregiver_headers(1)).json()[0]
    upload_face(
        client,
        patient_id=1,
        person_id=sarah["id"],
        caregiver_id=1,
        image_bytes=b"sarah-reference",
    )

    response = recognize_face(client, user_id=1, image_bytes=b"weak-camera")

    assert response.status_code == 200
    assert response.json() == {
        "recognized": False,
        "person_id": None,
        "name": None,
        "relationship": None,
        "confidence": 0.4,
    }


def test_face_recognition_returns_unknown_when_ambiguous(client: TestClient, monkeypatch) -> None:
    seed(client)
    monkeypatch.setattr(face_provider, "get_face_recognizer", lambda: StubFaceRecognizer())
    people = client.get("/api/caregiver/patients/1/people", headers=caregiver_headers(1)).json()
    sarah = people[0]
    emma = client.post(
        "/api/caregiver/patients/1/people",
        headers=caregiver_headers(1),
        json={"name": "Emma", "relationship": "Friend"},
    ).json()
    upload_face(
        client,
        patient_id=1,
        person_id=sarah["id"],
        caregiver_id=1,
        image_bytes=b"sarah-reference",
    )
    upload_face(
        client,
        patient_id=1,
        person_id=emma["id"],
        caregiver_id=1,
        image_bytes=b"emma-reference",
    )

    response = recognize_face(client, user_id=1, image_bytes=b"ambiguous-camera")

    assert response.status_code == 200
    assert response.json() == {
        "recognized": False,
        "person_id": None,
        "name": None,
        "relationship": None,
        "confidence": 0.82,
    }


def test_face_recognition_is_patient_scoped(client: TestClient, monkeypatch) -> None:
    seed(client)
    monkeypatch.setattr(face_provider, "get_face_recognizer", lambda: StubFaceRecognizer())
    sarah = client.get("/api/caregiver/patients/1/people", headers=caregiver_headers(1)).json()[0]
    upload_face(
        client,
        patient_id=1,
        person_id=sarah["id"],
        caregiver_id=1,
        image_bytes=b"sarah-reference",
    )

    response = recognize_face(client, user_id=2, image_bytes=b"sarah-camera")

    assert response.status_code == 200
    assert response.json()["recognized"] is False
    assert response.json()["name"] is None


def test_other_patient_enrollment_is_not_visible(client: TestClient, monkeypatch) -> None:
    seed(client)
    monkeypatch.setattr(face_provider, "get_face_recognizer", lambda: StubFaceRecognizer())
    alex_sarah = client.get("/api/caregiver/patients/1/people", headers=caregiver_headers(1)).json()[0]
    jordan_sarah = client.get("/api/caregiver/patients/2/people", headers=caregiver_headers(2)).json()[0]
    upload_face(
        client,
        patient_id=1,
        person_id=alex_sarah["id"],
        caregiver_id=1,
        image_bytes=b"sarah-reference",
    )
    upload_face(
        client,
        patient_id=2,
        person_id=jordan_sarah["id"],
        caregiver_id=2,
        image_bytes=b"jordan-reference",
    )

    alex_result = recognize_face(client, user_id=1, image_bytes=b"sarah-camera")
    jordan_result = recognize_face(client, user_id=2, image_bytes=b"sarah-camera")

    assert alex_result.json()["name"] == "Sarah"
    assert alex_result.json()["relationship"] == "Daughter"
    assert jordan_result.json()["recognized"] is False
    assert jordan_result.json()["name"] is None


def test_face_embedding_not_returned_by_api(client: TestClient, monkeypatch) -> None:
    seed(client)
    monkeypatch.setattr(face_provider, "get_face_recognizer", lambda: StubFaceRecognizer())
    sarah = client.get("/api/caregiver/patients/1/people", headers=caregiver_headers(1)).json()[0]
    enrollment = upload_face(
        client,
        patient_id=1,
        person_id=sarah["id"],
        caregiver_id=1,
        image_bytes=b"sarah-reference",
    )
    status = client.get(
        f"/api/caregiver/patients/1/people/{sarah['id']}/face/status",
        headers=caregiver_headers(3),
    )
    people = client.get("/api/caregiver/patients/1/people", headers=caregiver_headers(3))

    assert enrollment.status_code == 200
    assert status.status_code == 200
    assert "embedding" not in enrollment.json()
    assert "embedding" not in status.json()
    assert all("embedding" not in person for person in people.json())


def test_delete_face_enrollment(client: TestClient, monkeypatch) -> None:
    seed(client)
    monkeypatch.setattr(face_provider, "get_face_recognizer", lambda: StubFaceRecognizer())
    sarah = client.get("/api/caregiver/patients/1/people", headers=caregiver_headers(1)).json()[0]
    upload_face(
        client,
        patient_id=1,
        person_id=sarah["id"],
        caregiver_id=1,
        image_bytes=b"sarah-reference",
    )

    deleted = client.delete(
        f"/api/caregiver/patients/1/people/{sarah['id']}/face",
        headers=caregiver_headers(1),
    )
    status = client.get(
        f"/api/caregiver/patients/1/people/{sarah['id']}/face/status",
        headers=caregiver_headers(1),
    )
    result = recognize_face(client, user_id=1, image_bytes=b"sarah-camera")

    assert deleted.status_code == 204
    assert status.json() == {"person_id": sarah["id"], "enrolled": False, "created_at": None}
    assert result.json()["recognized"] is False


def test_replace_face_enrollment(client: TestClient, monkeypatch) -> None:
    seed(client)
    monkeypatch.setattr(face_provider, "get_face_recognizer", lambda: StubFaceRecognizer())
    sarah = client.get("/api/caregiver/patients/1/people", headers=caregiver_headers(1)).json()[0]
    first = upload_face(
        client,
        patient_id=1,
        person_id=sarah["id"],
        caregiver_id=1,
        image_bytes=b"sarah-reference",
    )
    replaced = upload_face(
        client,
        patient_id=1,
        person_id=sarah["id"],
        caregiver_id=1,
        image_bytes=b"emma-reference",
    )

    old_status = first.json()
    new_status = replaced.json()
    old_result = recognize_face(client, user_id=1, image_bytes=b"sarah-camera")
    new_result = recognize_face(client, user_id=1, image_bytes=b"emma-camera")

    assert first.status_code == 200
    assert replaced.status_code == 200
    assert new_status["enrolled"] is True
    assert new_status["person_id"] == old_status["person_id"]
    assert old_result.json()["recognized"] is False
    assert new_result.json()["name"] == "Sarah"


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
    body = response.json()
    assert body["answer"] == "You were preparing to leave."
    assert body["intent"] == "recent_activity"
    assert body["source_ids"] == ["memory:4"]
    assert body["language"] == "en"
    assert [item["source_id"] for item in body["evidence"]] == ["memory:4"]


def test_keys_last_seen_query(client: TestClient) -> None:
    seed(client)
    response = client.post("/api/query", json={"question": "Where are my keys?"})
    body = response.json()
    assert body["answer"] == "Last recorded: your keys on the kitchen counter at 10:18 AM."
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
        "answer": "I couldn't find matching saved information for that.",
        "intent": "unknown",
        "source_ids": [],
        "evidence": [],
        "language": "en",
    }


@pytest.mark.parametrize(
    "question",
    [
        "what was i just doing",
        "What did I do a moment ago?",
        "what was I doing",
    ],
)
def test_recent_activity_accepts_spoken_phrasings(client: TestClient, question: str) -> None:
    seed(client)
    response = client.post("/api/query", json={"question": question})
    body = response.json()
    assert body["intent"] == "recent_activity"
    assert body["answer"] == "You were preparing to leave."


def test_object_question_resolves_any_observed_object(client: TestClient) -> None:
    seed(client)
    upload = upload_memory(
        client,
        timestamp=timestamp_at(hour=11, minute=5),
        location="hallway shelf",
        description="Reading glasses left on the shelf.",
        object_name="glasses",
    )
    assert upload.status_code == 201
    response = client.post("/api/query", json={"question": "Where did I leave my glasses?"})
    body = response.json()
    assert body["intent"] == "object_location"
    assert body["answer"].startswith("Last recorded: your glasses on the hallway shelf at ")


def test_object_question_is_unknown_for_an_untracked_object(client: TestClient) -> None:
    seed(client)
    response = client.post("/api/query", json={"question": "Where is my passport?"})
    body = response.json()
    assert body["intent"] == "unknown"
    assert body["evidence"] == []


@pytest.mark.parametrize(
    "question",
    [
        "Where is my passport today?",
        "Where is my passport, not my keys?",
    ],
)
def test_untracked_object_stays_unknown_next_to_known_words(
    client: TestClient, question: str
) -> None:
    seed(client)
    body = client.post("/api/query", json={"question": question}).json()
    assert body["intent"] == "unknown"
    assert body["evidence"] == []


def test_person_question_uses_the_full_name_that_was_asked(client: TestClient) -> None:
    seed(client)
    body = client.post("/api/query", json={"question": "Who is Sarah Zorblax?"}).json()
    assert body["intent"] == "unknown"
    assert body["evidence"] == []


def test_person_question_resolves_any_stored_person(client: TestClient) -> None:
    seed(client)
    response = client.post(
        "/api/caregiver/patients/1/people",
        headers={CAREGIVER_ID_HEADER: "1"},
        json={"name": "Omar", "relationship": "Neighbor"},
    )
    assert response.status_code == 201
    body = client.post("/api/query", json={"question": "Who is Omar?"}).json()
    assert body["intent"] == "person_lookup"
    assert body["answer"] == "Omar is your neighbor."


def test_answers_carry_evidence_with_timestamps(client: TestClient) -> None:
    seed(client)
    body = client.post("/api/query", json={"question": "Where are my keys?"}).json()
    evidence = body["evidence"]
    assert [item["source_id"] for item in evidence] == body["source_ids"]
    assert evidence[0]["detail"] == "kitchen counter"
    assert evidence[0]["recorded_at"] is not None


def test_arabic_answers_stay_grounded_in_stored_records(client: TestClient) -> None:
    seed(client)
    body = client.post(
        "/api/query",
        json={"question": "أين مفاتيحي؟", "language": "ar"},
    ).json()
    assert body["intent"] == "object_location"
    assert body["language"] == "ar"
    assert "kitchen counter" in body["answer"]
    assert "صباحًا" in body["answer"]


def test_arabic_unknown_answer_refuses_to_guess(client: TestClient) -> None:
    seed(client)
    body = client.post(
        "/api/query",
        json={"question": "What is the weather?", "language": "ar"},
    ).json()
    assert body["intent"] == "unknown"
    assert body["answer"] == "لا أملك معلومات محفوظة عن ذلك، ولن أخمّن."


def test_seed_can_be_run_twice_without_duplicate_demo_state(client: TestClient) -> None:
    first = client.post("/api/demo/seed")
    second = client.post("/api/demo/seed")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == {
        "status": "ok",
        "user_ids": [1, 2],
        "user_count": 2,
        "caregiver_ids": [1, 2, 3],
        "caregiver_count": 3,
        "access_count": 3,
        "profile_count": 2,
        "memory_count": 8,
        "observation_count": 2,
        "person_count": 2,
        "schedule_count": 4,
        "important_object_count": 4,
        "note_count": 2,
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
        "Last recorded: your keys on the Kitchen counter at 10:42 AM."
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
        "Last recorded: your keys on the bedroom desk at 10:42 AM."
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


def test_vision_analysis_uses_grounded_fallback_for_bundled_demo_scene(
    client: TestClient, monkeypatch
) -> None:
    seed(client)
    monkeypatch.setattr(
        vision_provider,
        "get_vision_analyzer",
        lambda: (_ for _ in ()).throw(AssertionError("provider must not be called")),
    )
    response = client.post(
        "/api/vision/analyze",
        files={"image": ("keys-on-table.jpg", b"fake-image-content", "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "description": "A set of keys is resting beside a phone and headphones on a dark table.",
        "location": "Table",
        "activity": "Preparing to leave",
        "objects": [{"name": "keys", "location": "dark table", "confidence": 0.99}],
    }


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

    assert alex_keys["answer"] == "Last recorded: your keys on the kitchen counter at 10:18 AM."
    assert jordan_keys["answer"] == "Last recorded: your keys on the bedroom desk at 10:24 AM."
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
    assert alex_answer == "Last recorded: your keys on the Alex table at 11:03 AM."
    assert jordan_answer == "Last recorded: your keys on the Jordan shelf at 11:04 AM."


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


def test_caregiver_identity_is_required_and_separate_from_patient_identity(client: TestClient) -> None:
    seed(client)
    with TestClient(app) as anonymous_client:
        missing = anonymous_client.get("/api/caregiver/patients")
    patient_header_only = client.get("/api/caregiver/patients", headers=user_headers(1))

    assert missing.status_code == 401
    assert missing.json() == {"detail": "Caregiver identity is required."}
    assert patient_header_only.status_code == 401
    assert patient_header_only.json() == {"detail": "Caregiver identity is required."}


def test_unknown_caregiver_identity_is_rejected(client: TestClient) -> None:
    seed(client)
    response = client.get(
        "/api/caregiver/patients",
        headers=caregiver_headers(999),
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Caregiver not found."}


def test_caregivers_only_list_linked_patients(client: TestClient) -> None:
    seed(client)
    maya = client.get("/api/caregiver/patients", headers=caregiver_headers(1))
    sam = client.get("/api/caregiver/patients", headers=caregiver_headers(2))
    taylor = client.get("/api/caregiver/patients", headers=caregiver_headers(3))

    assert maya.json() == [{
        "user_id": 1,
        "name": "Alex",
        "preferred_name": "Alex",
        "role": "primary",
        "can_manage_profile": True,
        "can_manage_people": True,
        "can_manage_schedule": True,
        "can_manage_objects": True,
        "can_manage_notes": True,
    }]
    assert sam.json() == [{
        "user_id": 2,
        "name": "Jordan",
        "preferred_name": "Jordan",
        "role": "primary",
        "can_manage_profile": True,
        "can_manage_people": True,
        "can_manage_schedule": True,
        "can_manage_objects": True,
        "can_manage_notes": True,
    }]
    assert taylor.json() == [{
        "user_id": 1,
        "name": "Alex",
        "preferred_name": "Alex",
        "role": "viewer",
        "can_manage_profile": False,
        "can_manage_people": False,
        "can_manage_schedule": False,
        "can_manage_objects": False,
        "can_manage_notes": False,
    }]

    maya_cannot_open_jordan = client.get(
        "/api/caregiver/patients/2/profile",
        headers=caregiver_headers(1),
    )
    sam_cannot_open_alex = client.get(
        "/api/caregiver/patients/1/profile",
        headers=caregiver_headers(2),
    )
    assert maya_cannot_open_jordan.status_code == 404
    assert sam_cannot_open_alex.status_code == 404


def test_patient_profile_permissions_and_persistence(client: TestClient) -> None:
    seed(client)
    profile_response = client.get(
        "/api/caregiver/patients/1/profile",
        headers=caregiver_headers(1),
    )
    assert profile_response.status_code == 200
    assert profile_response.json()["response_style"] == "Short, calm reminders"

    update_response = client.patch(
        "/api/caregiver/patients/1/profile",
        headers=caregiver_headers(1),
        json={"home_context": "Lives at home with a quiet routine", "response_style": "calm"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["home_context"] == "Lives at home with a quiet routine"
    assert update_response.json()["response_style"] == "calm"

    viewer_update = client.patch(
        "/api/caregiver/patients/1/profile",
        headers=caregiver_headers(3),
        json={"response_style": "factual"},
    )
    sam_update = client.patch(
        "/api/caregiver/patients/1/profile",
        headers=caregiver_headers(2),
        json={"response_style": "factual"},
    )
    assert viewer_update.status_code == 403
    assert sam_update.status_code == 404


def test_people_crud_is_scoped_and_updates_patient_query(client: TestClient) -> None:
    seed(client)
    people = client.get("/api/caregiver/patients/1/people", headers=caregiver_headers(1))
    sarah = next(person for person in people.json() if person["name"] == "Sarah")
    update = client.patch(
        f"/api/caregiver/patients/1/people/{sarah['id']}",
        headers=caregiver_headers(1),
        json={"relationship": "Daughter and primary family contact"},
    )
    assert update.status_code == 200
    assert update.json()["relationship"] == "Daughter and primary family contact"

    query_response = client.post(
        "/api/query",
        headers=user_headers(1),
        json={"question": "Who is Sarah?"},
    )
    assert query_response.json()["answer"] == (
        "Sarah is your daughter and primary family contact."
    )

    created = client.post(
        "/api/caregiver/patients/1/people",
        headers=caregiver_headers(1),
        json={"name": "Maya", "relationship": "Caregiver"},
    )
    assert created.status_code == 201
    changed = client.patch(
        f"/api/caregiver/patients/1/people/{created.json()['id']}",
        headers=caregiver_headers(1),
        json={"name": "Maya Patel"},
    )
    deleted = client.delete(
        f"/api/caregiver/patients/1/people/{created.json()['id']}",
        headers=caregiver_headers(1),
    )
    assert changed.status_code == 200
    assert deleted.status_code == 204

    jordan_person = client.get(
        "/api/caregiver/patients/2/people",
        headers=caregiver_headers(2),
    ).json()[0]
    unauthorized_edit = client.patch(
        f"/api/caregiver/patients/2/people/{jordan_person['id']}",
        headers=caregiver_headers(1),
        json={"relationship": "Unauthorized"},
    )
    viewer_create = client.post(
        "/api/caregiver/patients/1/people",
        headers=caregiver_headers(3),
        json={"name": "Viewer", "relationship": "Observer"},
    )
    assert unauthorized_edit.status_code == 404
    assert viewer_create.status_code == 403


def test_important_objects_are_definitions_separate_from_observations(client: TestClient) -> None:
    seed(client)
    created = client.post(
        "/api/caregiver/patients/1/objects",
        headers=caregiver_headers(1),
        json={"name": "Glasses", "notes": "Usually kept by the reading chair"},
    )
    assert created.status_code == 201
    object_id = created.json()["id"]
    updated = client.patch(
        f"/api/caregiver/patients/1/objects/{object_id}",
        headers=caregiver_headers(1),
        json={"notes": "Keep in the protective case"},
    )
    assert updated.status_code == 200
    assert updated.json()["notes"] == "Keep in the protective case"

    keys_answer = client.post(
        "/api/query",
        headers=user_headers(1),
        json={"question": "Where are my keys?"},
    )
    assert keys_answer.json()["answer"] == "Last recorded: your keys on the kitchen counter at 10:18 AM."

    deleted = client.delete(
        f"/api/caregiver/patients/1/objects/{object_id}",
        headers=caregiver_headers(1),
    )
    jordan_object = client.get(
        "/api/caregiver/patients/2/objects",
        headers=caregiver_headers(2),
    ).json()[0]
    unauthorized_edit = client.patch(
        f"/api/caregiver/patients/2/objects/{jordan_object['id']}",
        headers=caregiver_headers(1),
        json={"notes": "Unauthorized"},
    )
    assert deleted.status_code == 204
    assert unauthorized_edit.status_code == 404


def test_schedule_crud_flows_into_patient_query(client: TestClient) -> None:
    seed(client)
    created = client.post(
        "/api/caregiver/patients/1/schedule",
        headers=caregiver_headers(1),
        json={"title": "Family walk", "scheduled_at": timestamp_at(12, 1)},
    )
    assert created.status_code == 201
    item_id = created.json()["id"]
    updated = client.patch(
        f"/api/caregiver/patients/1/schedule/{item_id}",
        headers=caregiver_headers(1),
        json={"title": "Walk with Maya"},
    )
    assert updated.status_code == 200

    query_response = client.post(
        "/api/query",
        headers=user_headers(1),
        json={"question": "What am I doing today?"},
    )
    assert query_response.json()["answer"].startswith("Walk with Maya at 12:01 PM.")

    deleted = client.delete(
        f"/api/caregiver/patients/1/schedule/{item_id}",
        headers=caregiver_headers(1),
    )
    jordan_item = client.get(
        "/api/caregiver/patients/2/schedule",
        headers=caregiver_headers(2),
    ).json()[0]
    unauthorized_edit = client.patch(
        f"/api/caregiver/patients/2/schedule/{jordan_item['id']}",
        headers=caregiver_headers(1),
        json={"title": "Unauthorized"},
    )
    assert deleted.status_code == 204
    assert unauthorized_edit.status_code == 404


def test_caregiver_notes_are_scoped_and_record_author(client: TestClient) -> None:
    seed(client)
    created = client.post(
        "/api/caregiver/patients/1/notes",
        headers=caregiver_headers(1),
        json={"note": "Keep the front entrance clear before Sarah visits."},
    )
    assert created.status_code == 201
    assert created.json()["caregiver_id"] == 1
    note_id = created.json()["id"]

    maya_notes = client.get(
        "/api/caregiver/patients/1/notes",
        headers=caregiver_headers(1),
    ).json()
    assert any(note["id"] == note_id for note in maya_notes)
    maya_cannot_read_jordan = client.get(
        "/api/caregiver/patients/2/notes",
        headers=caregiver_headers(1),
    )
    sam_cannot_write_alex = client.post(
        "/api/caregiver/patients/1/notes",
        headers=caregiver_headers(2),
        json={"note": "Unauthorized note"},
    )
    assert maya_cannot_read_jordan.status_code == 404
    assert sam_cannot_write_alex.status_code == 404

    deleted = client.delete(
        f"/api/caregiver/patients/1/notes/{note_id}",
        headers=caregiver_headers(1),
    )
    assert deleted.status_code == 204


def test_schedule_cue_within_lookahead(client: TestClient, monkeypatch) -> None:
    seed(client)
    clear_schedule(client, 1)
    monkeypatch.setenv("CUE_SCHEDULE_LOOKAHEAD_MINUTES", "30")
    monkeypatch.setenv("CUE_OBJECT_LOOKBACK_MINUTES", "0")

    created = client.post(
        "/api/caregiver/patients/1/schedule",
        headers=caregiver_headers(1),
        json={"title": "Sarah visits", "scheduled_at": timestamp_in(10)},
    )
    assert created.status_code == 201

    response = client.get("/api/cues", headers=user_headers(1))

    assert response.status_code == 200
    assert response.json()["cues"][0]["type"] == "schedule_upcoming"
    assert response.json()["cues"][0]["title"] == "Coming up"
    assert response.json()["cues"][0]["message"].startswith("Sarah visits at")
    assert response.json()["cues"][0]["source_ids"] == [f"schedule:{created.json()['id']}"]


def test_schedule_cue_not_returned_outside_window(client: TestClient, monkeypatch) -> None:
    seed(client)
    clear_schedule(client, 1)
    monkeypatch.setenv("CUE_SCHEDULE_LOOKAHEAD_MINUTES", "30")
    monkeypatch.setenv("CUE_OBJECT_LOOKBACK_MINUTES", "0")

    created = client.post(
        "/api/caregiver/patients/1/schedule",
        headers=caregiver_headers(1),
        json={"title": "Later visit", "scheduled_at": timestamp_in(31)},
    )
    assert created.status_code == 201

    response = client.get("/api/cues", headers=user_headers(1))

    assert response.status_code == 200
    assert response.json() == {"cues": []}


def test_schedule_cue_is_user_scoped(client: TestClient, monkeypatch) -> None:
    seed(client)
    clear_schedule(client, 1)
    clear_schedule(client, 2)
    monkeypatch.setenv("CUE_OBJECT_LOOKBACK_MINUTES", "0")

    created = client.post(
        "/api/caregiver/patients/1/schedule",
        headers=caregiver_headers(1),
        json={"title": "Alex visit", "scheduled_at": timestamp_in(10)},
    )
    assert created.status_code == 201

    response = client.get("/api/cues", headers=user_headers(2))

    assert response.status_code == 200
    assert response.json() == {"cues": []}


def test_cue_reads_are_observational_until_presentation_is_acknowledged(client: TestClient, monkeypatch) -> None:
    seed(client)
    clear_schedule(client, 1)
    monkeypatch.setenv("CUE_COOLDOWN_MINUTES", "20")
    monkeypatch.setenv("CUE_OBJECT_LOOKBACK_MINUTES", "0")
    created = client.post(
        "/api/caregiver/patients/1/schedule",
        headers=caregiver_headers(1),
        json={"title": "A near-term appointment", "scheduled_at": timestamp_in(10)},
    )
    assert created.status_code == 201

    first = client.get("/api/cues", headers=user_headers(1))
    second = client.get("/api/cues", headers=user_headers(1))

    assert len(first.json()["cues"]) == 1
    assert second.json() == first.json()

    cue_id = first.json()["cues"][0]["id"]
    presented = client.post(
        "/api/cues/present",
        headers=user_headers(1),
        json={
            "cue_id": cue_id,
            "presentation_id": "00000000-0000-4000-8000-000000000001",
        },
    )
    suppressed = client.get("/api/cues", headers=user_headers(1))

    assert presented.status_code == 200
    assert presented.json()["status"] == "presented"
    assert suppressed.json() == {"cues": []}


def test_duplicate_presentation_acknowledgement_does_not_extend_cooldown(client: TestClient, monkeypatch) -> None:
    seed(client)
    clear_schedule(client, 1)
    monkeypatch.setenv("CUE_COOLDOWN_MINUTES", "20")
    monkeypatch.setenv("CUE_SCHEDULE_LOOKAHEAD_MINUTES", "60")
    monkeypatch.setenv("CUE_OBJECT_LOOKBACK_MINUTES", "0")
    initial_time = datetime.now().replace(second=0, microsecond=0)

    class ControlledDateTime(datetime):
        current = initial_time

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(cue_routes, "datetime", ControlledDateTime)
    monkeypatch.setattr(cue_service, "datetime", ControlledDateTime)
    created = client.post(
        "/api/caregiver/patients/1/schedule",
        headers=caregiver_headers(1),
        json={"title": "A later appointment", "scheduled_at": (initial_time + timedelta(minutes=50)).isoformat()},
    )
    assert created.status_code == 201
    cue_id = client.get("/api/cues", headers=user_headers(1)).json()["cues"][0]["id"]
    payload = {
        "cue_id": cue_id,
        "presentation_id": "00000000-0000-4000-8000-000000000002",
    }

    first = client.post("/api/cues/present", headers=user_headers(1), json=payload)
    ControlledDateTime.current = initial_time + timedelta(minutes=10)
    duplicate = client.post("/api/cues/present", headers=user_headers(1), json=payload)
    competing = client.post(
        "/api/cues/present",
        headers=user_headers(1),
        json={
            "cue_id": cue_id,
            "presentation_id": "00000000-0000-4000-8000-000000000003",
        },
    )
    ControlledDateTime.current = initial_time + timedelta(minutes=21)
    after_original_cooldown = client.get("/api/cues", headers=user_headers(1))

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "already_presented"
    assert duplicate.json()["presented_at"] == first.json()["presented_at"]
    assert competing.status_code == 409
    assert len(after_original_cooldown.json()["cues"]) == 1


def test_presentation_acknowledgement_validates_patient_context(client: TestClient, monkeypatch) -> None:
    seed(client)
    clear_schedule(client, 1)
    clear_schedule(client, 2)
    monkeypatch.setenv("CUE_OBJECT_LOOKBACK_MINUTES", "0")
    created = client.post(
        "/api/caregiver/patients/1/schedule",
        headers=caregiver_headers(1),
        json={"title": "Alex appointment", "scheduled_at": timestamp_in(10)},
    )
    assert created.status_code == 201
    cue_id = client.get("/api/cues", headers=user_headers(1)).json()["cues"][0]["id"]

    other_patient = client.post(
        "/api/cues/present",
        headers=user_headers(2),
        json={
            "cue_id": cue_id,
            "presentation_id": "00000000-0000-4000-8000-000000000004",
        },
    )
    unknown_cue = client.post(
        "/api/cues/present",
        headers=user_headers(1),
        json={
            "cue_id": "schedule:99999",
            "presentation_id": "00000000-0000-4000-8000-000000000005",
        },
    )

    assert other_patient.status_code == 409
    assert unknown_cue.status_code == 409


def test_dismissed_cue_does_not_reappear(client: TestClient, monkeypatch) -> None:
    seed(client)
    clear_schedule(client, 1)
    monkeypatch.setenv("CUE_OBJECT_LOOKBACK_MINUTES", "0")
    created = client.post(
        "/api/caregiver/patients/1/schedule",
        headers=caregiver_headers(1),
        json={"title": "A visit to dismiss", "scheduled_at": timestamp_in(10)},
    )
    assert created.status_code == 201
    first = client.get("/api/cues", headers=user_headers(1))
    cue_id = first.json()["cues"][0]["id"]

    dismissed = client.post(f"/api/cues/{cue_id}/dismiss", headers=user_headers(1))
    again = client.get("/api/cues", headers=user_headers(1))

    assert dismissed.status_code == 200
    assert dismissed.json() == {"status": "dismissed", "cue_id": cue_id}
    assert again.json() == {"cues": []}


def test_recognized_person_cue_uses_stored_relationship(client: TestClient, monkeypatch) -> None:
    seed(client)
    clear_schedule(client, 1)
    monkeypatch.setenv("CUE_OBJECT_LOOKBACK_MINUTES", "0")
    monkeypatch.setattr(face_provider, "get_face_recognizer", lambda: StubFaceRecognizer())
    sarah = client.get("/api/caregiver/patients/1/people", headers=caregiver_headers(1)).json()[0]
    enrollment = upload_face(
        client,
        patient_id=1,
        person_id=sarah["id"],
        caregiver_id=1,
        image_bytes=b"sarah-reference",
    )
    assert enrollment.status_code == 200

    recognition = recognize_face(client, user_id=1, image_bytes=b"sarah-camera")
    response = client.get("/api/cues", headers=user_headers(1))

    assert recognition.status_code == 200
    assert response.status_code == 200
    cue = response.json()["cues"][0]
    assert cue["type"] == "recognized_person"
    assert cue["title"] == "Sarah"
    assert cue["message"] == "Your daughter."
    assert f"person:{sarah['id']}" in cue["source_ids"]


def test_recognized_person_cue_is_patient_scoped(client: TestClient, monkeypatch) -> None:
    seed(client)
    clear_schedule(client, 1)
    clear_schedule(client, 2)
    monkeypatch.setenv("CUE_OBJECT_LOOKBACK_MINUTES", "0")
    monkeypatch.setattr(face_provider, "get_face_recognizer", lambda: StubFaceRecognizer())
    sarah = client.get("/api/caregiver/patients/1/people", headers=caregiver_headers(1)).json()[0]
    enrollment = upload_face(
        client,
        patient_id=1,
        person_id=sarah["id"],
        caregiver_id=1,
        image_bytes=b"sarah-reference",
    )
    assert enrollment.status_code == 200
    assert recognize_face(client, user_id=1, image_bytes=b"sarah-camera").status_code == 200

    response = client.get("/api/cues", headers=user_headers(2))

    assert response.status_code == 200
    assert response.json() == {"cues": []}


def test_no_cue_when_context_is_insufficient(client: TestClient, monkeypatch) -> None:
    seed(client)
    clear_schedule(client, 1)
    monkeypatch.setenv("CUE_OBJECT_LOOKBACK_MINUTES", "0")

    response = client.get("/api/cues", headers=user_headers(1))

    assert response.status_code == 200
    assert response.json() == {"cues": []}


def test_important_object_cue_uses_last_seen_language(client: TestClient, monkeypatch) -> None:
    seed(client)
    clear_schedule(client, 1)
    monkeypatch.setenv("CUE_OBJECT_LOOKBACK_MINUTES", "30")
    recent_timestamp = datetime.now().replace(second=0, microsecond=0).isoformat(timespec="seconds")
    created = upload_memory(
        client,
        timestamp=recent_timestamp,
        location="hallway table",
        description="Keys were placed on the hallway table before leaving.",
        activity="preparing to leave",
        object_name="keys",
        filename="recent-keys.jpg",
    )
    assert created.status_code == 201

    response = client.get("/api/cues", headers=user_headers(1))

    assert response.status_code == 200
    cue = response.json()["cues"][0]
    assert cue["type"] == "important_object"
    assert cue["title"] == "keys"
    assert cue["message"] == "Last seen at hallway table."
    assert f"object_observation:{created.json()['object_observation_id']}" in cue["source_ids"]


def test_cues_endpoint_requires_identity(client: TestClient) -> None:
    with TestClient(app) as anonymous_client:
        response = anonymous_client.get("/api/cues")

    assert response.status_code == 401
    assert response.json() == {"detail": "User identity is required."}


def test_rewind_returns_the_three_newest_saved_moments_in_order(client: TestClient) -> None:
    seed(client)
    for minutes, location, activity in (
        (-8, "Kitchen", "pouring water"),
        (-5, "Porch", "checking the post"),
        (-3, "Study", "sorting papers"),
        (-1, "Hallway", "putting on shoes"),
    ):
        created = upload_memory(
            client,
            timestamp=timestamp_in(minutes),
            location=location,
            description=f"{activity} at {location}.",
            activity=activity,
            filename=f"moment{abs(minutes)}.jpg",
        )
        assert created.status_code == 201

    body = client.get("/api/rewind", headers=user_headers(1)).json()

    assert body["within_window"] is True
    assert [moment["location"] for moment in body["moments"]] == ["Porch", "Study", "Hallway"]
    assert all(moment["image_url"] for moment in body["moments"])
    assert all(moment["source"] == "photo" for moment in body["moments"])
    assert "3 saved moments" in body["summary"]
    assert "Hallway" in body["summary"]


def test_rewind_excludes_moments_older_than_the_window(client: TestClient) -> None:
    seed(client)
    old = upload_memory(
        client,
        timestamp=timestamp_in(-45),
        location="Garden",
        description="Watering the garden.",
        activity="watering the garden",
    )
    assert old.status_code == 201

    body = client.get("/api/rewind", headers=user_headers(1)).json()

    assert body["moments"] == []
    assert body["within_window"] is False
    assert body["has_earlier"] is True
    assert "last 10 minutes" in body["summary"]


def test_rewind_can_show_earlier_saved_moments_on_request(client: TestClient) -> None:
    seed(client)
    created = upload_memory(
        client,
        timestamp=timestamp_in(-45),
        location="Garden",
        description="Watering the garden.",
        activity="watering the garden",
    )
    assert created.status_code == 201

    body = client.get(
        "/api/rewind",
        params={"include_earlier": "true"},
        headers=user_headers(1),
    ).json()

    assert body["within_window"] is False
    assert body["moments"][-1]["location"] == "Garden"
    assert "not continuous recording" in body["summary"]


def test_rewind_only_includes_the_selected_profile(client: TestClient) -> None:
    seed(client)
    alex = upload_memory(
        client,
        timestamp=timestamp_in(-2),
        location="Kitchen",
        description="Alex put a cup down.",
        user_id=1,
    )
    jordan = upload_memory(
        client,
        timestamp=timestamp_in(-2),
        location="Bedroom",
        description="Jordan folded a shirt.",
        user_id=2,
    )
    assert alex.status_code == 201
    assert jordan.status_code == 201

    body = client.get("/api/rewind", headers=user_headers(2)).json()

    assert [moment["location"] for moment in body["moments"]] == ["Bedroom"]
    assert body["moments"][0]["image_url"] != alex.json()["image_url"]


def test_object_answer_evidence_links_to_the_saved_photo(client: TestClient) -> None:
    seed(client)
    created = upload_memory(
        client,
        timestamp=timestamp_in(-4),
        location="hallway table",
        description="Wallet left on the hallway table.",
        object_name="wallet",
        filename="wallet.jpg",
    )
    assert created.status_code == 201

    body = client.post(
        "/api/query",
        json={"question": "Have you seen my wallet anywhere?"},
    ).json()

    assert body["intent"] == "object_location"
    assert "hallway table" in body["answer"]
    assert body["evidence"][0]["image_url"] == created.json()["image_url"]


def test_object_answer_uses_the_newest_observation(client: TestClient) -> None:
    seed(client)
    older = upload_memory(
        client,
        timestamp=timestamp_in(-30),
        location="kitchen counter",
        description="Bag on the kitchen counter.",
        object_name="bag",
        filename="bag-old.jpg",
    )
    newer = upload_memory(
        client,
        timestamp=timestamp_in(-5),
        location="front door hook",
        description="Bag on the front door hook.",
        object_name="bag",
        filename="bag-new.jpg",
    )
    assert older.status_code == 201
    assert newer.status_code == 201

    body = client.post("/api/query", json={"question": "Where did I put my bag?"}).json()

    assert "front door hook" in body["answer"]
    assert "kitchen counter" not in body["answer"]
    assert body["evidence"][0]["image_url"] == newer.json()["image_url"]


def test_caregiver_correction_changes_later_answers_and_keeps_history(client: TestClient) -> None:
    seed(client)
    created = upload_memory(
        client,
        timestamp=timestamp_in(-6),
        location="kitchen counter",
        description="Keys on the kitchen counter.",
        object_name="keys",
        filename="keys.jpg",
    )
    assert created.status_code == 201
    memory_id = created.json()["id"]

    corrected = client.post(
        f"/api/caregiver/patients/1/moments/{memory_id}/corrections",
        json={"field": "object_location", "value": "hallway shelf"},
        headers=caregiver_headers(1),
    )
    assert corrected.status_code == 201
    body = corrected.json()
    assert body["object_location"] == "hallway shelf"
    assert body["recorded_at"] == created.json()["timestamp"]
    assert body["image_url"] == created.json()["image_url"]

    history = body["corrections"]
    assert len(history) == 1
    assert history[0]["old_value"] == "kitchen counter"
    assert history[0]["new_value"] == "hallway shelf"
    assert history[0]["caregiver_name"] == "Maya"
    assert history[0]["corrected_at"] != body["recorded_at"]

    answer = client.post("/api/query", json={"question": "Where are my keys?"}).json()
    assert "hallway shelf" in answer["answer"]
    assert "kitchen counter" not in answer["answer"]
    assert answer["evidence"][0]["corrected_by"] == "Maya"

    moment = client.get("/api/rewind", headers=user_headers(1)).json()["moments"][-1]
    assert moment["corrected_by"] == "Maya"
    assert moment["recorded_at"] == created.json()["timestamp"]


def test_a_viewer_caregiver_cannot_correct_a_saved_moment(client: TestClient) -> None:
    seed(client)
    created = upload_memory(
        client,
        timestamp=timestamp_in(-6),
        location="kitchen counter",
        description="Keys on the kitchen counter.",
        object_name="keys",
        filename="keys.jpg",
    )
    memory_id = created.json()["id"]

    rejected = client.post(
        f"/api/caregiver/patients/1/moments/{memory_id}/corrections",
        json={"field": "object_location", "value": "hallway shelf"},
        headers=caregiver_headers(3),
    )

    assert rejected.status_code == 403
    answer = client.post("/api/query", json={"question": "Where are my keys?"}).json()
    assert "kitchen counter" in answer["answer"]


def test_a_caregiver_cannot_correct_another_patients_moment(client: TestClient) -> None:
    seed(client)
    created = upload_memory(
        client,
        timestamp=timestamp_in(-6),
        location="kitchen counter",
        description="Keys on the kitchen counter.",
        object_name="keys",
        filename="keys.jpg",
    )
    memory_id = created.json()["id"]

    rejected = client.post(
        f"/api/caregiver/patients/1/moments/{memory_id}/corrections",
        json={"field": "object_location", "value": "hallway shelf"},
        headers=caregiver_headers(2),
    )

    assert rejected.status_code == 404


def test_a_new_observation_supersedes_a_corrected_one(client: TestClient) -> None:
    seed(client)
    created = upload_memory(
        client,
        timestamp=timestamp_in(-30),
        location="kitchen counter",
        description="Keys on the kitchen counter.",
        object_name="keys",
        filename="keys-old.jpg",
    )
    memory_id = created.json()["id"]
    client.post(
        f"/api/caregiver/patients/1/moments/{memory_id}/corrections",
        json={"field": "object_location", "value": "hallway shelf"},
        headers=caregiver_headers(1),
    )
    moved = upload_memory(
        client,
        timestamp=timestamp_in(-2),
        location="coat pocket",
        description="Keys in the coat pocket.",
        object_name="keys",
        filename="keys-new.jpg",
    )
    assert moved.status_code == 201

    answer = client.post("/api/query", json={"question": "Where are my keys?"}).json()

    assert "coat pocket" in answer["answer"]
    history = client.get(
        f"/api/caregiver/patients/1/moments/{memory_id}/corrections",
        headers=caregiver_headers(3),
    ).json()
    assert [entry["new_value"] for entry in history] == ["hallway shelf"]


def test_a_corrected_description_keeps_the_original_capture(client: TestClient) -> None:
    seed(client)
    created = upload_memory(
        client,
        timestamp=timestamp_in(-4),
        location="Kitchen",
        description="Making tea.",
        activity="making tea",
        filename="tea.jpg",
    )
    memory_id = created.json()["id"]

    corrected = client.post(
        f"/api/caregiver/patients/1/moments/{memory_id}/corrections",
        json={"field": "description", "value": "Making coffee."},
        headers=caregiver_headers(1),
    ).json()

    assert corrected["description"] == "Making coffee."
    assert corrected["image_url"] == created.json()["image_url"]
    assert corrected["recorded_at"] == created.json()["timestamp"]
    assert corrected["corrections"][0]["old_value"] == "Making tea."


def test_a_corrected_description_reaches_the_recap_and_activity_answer(
    client: TestClient,
) -> None:
    seed(client)
    created = upload_memory(
        client,
        timestamp=timestamp_in(-4),
        location="Kitchen",
        description="Making tea.",
        activity="making tea",
        filename="tea-recap.jpg",
    )
    client.post(
        f"/api/caregiver/patients/1/moments/{created.json()['id']}/corrections",
        json={"field": "description", "value": "Making coffee."},
        headers=caregiver_headers(1),
    )

    recap = client.get("/api/rewind").json()
    activity = client.post(
        "/api/query", json={"question": "What was I just doing?"}
    ).json()

    assert "making coffee" in recap["summary"]
    assert "making tea" not in recap["summary"]
    assert "making coffee" in activity["answer"]


def test_a_mixed_case_object_correction_still_answers(client: TestClient) -> None:
    seed(client)
    created = upload_memory(
        client,
        timestamp=timestamp_in(-5),
        location="kitchen counter",
        description="Keys on the kitchen counter.",
        object_name="keys",
        filename="keys-case.jpg",
    )
    client.post(
        f"/api/caregiver/patients/1/moments/{created.json()['id']}/corrections",
        json={"field": "object_name", "value": "Keys"},
        headers=caregiver_headers(1),
    )

    answer = client.post("/api/query", json={"question": "Where are my keys?"}).json()

    assert answer["intent"] == "object_location"
    assert "kitchen counter" in answer["answer"]


def test_the_demo_can_be_reseeded_after_a_correction(client: TestClient) -> None:
    seed(client)
    created = upload_memory(
        client,
        timestamp=timestamp_in(-5),
        location="kitchen counter",
        description="Keys on the kitchen counter.",
        object_name="keys",
        filename="keys-reseed.jpg",
    )
    client.post(
        f"/api/caregiver/patients/1/moments/{created.json()['id']}/corrections",
        json={"field": "object_location", "value": "hallway shelf"},
        headers=caregiver_headers(1),
    )

    reseeded = client.post("/api/demo/seed")

    assert reseeded.status_code == 200
    moments = client.get(
        "/api/caregiver/patients/1/moments", headers=caregiver_headers(1)
    ).json()
    assert all(moment["corrections"] == [] for moment in moments)


def test_a_corrected_location_reaches_the_recap_and_its_card(client: TestClient) -> None:
    seed(client)
    created = upload_memory(
        client,
        timestamp=timestamp_in(-3),
        location="kitchen counter",
        description="Keys on the kitchen counter.",
        object_name="keys",
        filename="keys-recap.jpg",
    )
    client.post(
        f"/api/caregiver/patients/1/moments/{created.json()['id']}/corrections",
        json={"field": "object_location", "value": "blue drawer"},
        headers=caregiver_headers(1),
    )

    rewind = client.get("/api/rewind").json()

    assert "Keys on the blue drawer" in rewind["summary"]
    assert rewind["moments"][-1]["description"] == "Keys on the blue drawer."
    assert rewind["moments"][-1]["recorded_at"] == created.json()["timestamp"]


def test_a_corrected_activity_answer_names_the_caregiver(client: TestClient) -> None:
    seed(client)
    created = upload_memory(
        client,
        timestamp=timestamp_in(-3),
        location="Kitchen",
        description="Making tea.",
        activity="making tea",
        filename="tea-attribution.jpg",
    )
    client.post(
        f"/api/caregiver/patients/1/moments/{created.json()['id']}/corrections",
        json={"field": "description", "value": "Making coffee."},
        headers=caregiver_headers(1),
    )

    answer = client.post(
        "/api/query", json={"question": "What was I just doing?"}
    ).json()

    assert answer["evidence"][0]["corrected_by"] == "Maya"
    assert answer["evidence"][0]["corrected_at"] is not None
    assert answer["evidence"][0]["recorded_at"] == created.json()["timestamp"]


def test_a_correction_keeps_an_initialism_uppercase(client: TestClient) -> None:
    seed(client)
    created = upload_memory(
        client,
        timestamp=timestamp_in(-3),
        location="Kitchen",
        description="Making tea.",
        activity="making tea",
        filename="tea-initialism.jpg",
    )
    client.post(
        f"/api/caregiver/patients/1/moments/{created.json()['id']}/corrections",
        json={"field": "description", "value": "QA checking the kettle."},
        headers=caregiver_headers(1),
    )

    answer = client.post(
        "/api/query", json={"question": "What was I just doing?"}
    ).json()

    assert "QA checking the kettle" in answer["answer"]

def test_deployed_origins_are_added_to_the_local_ones(monkeypatch) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://memorycue.vercel.app/, http://localhost:3000")

    origins = allowed_origins()

    assert origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://memorycue.vercel.app",
    ]


def test_an_empty_database_is_seeded_once(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'startup.db'}")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as first_session:
        assert seed_if_empty(first_session) is True
    with session_factory() as second_session:
        assert seed_if_empty(second_session) is False
        assert second_session.query(User).count() > 0

    engine.dispose()


def test_postgres_urls_are_pointed_at_the_installed_driver() -> None:
    assert (
        normalize_database_url("postgres://user:pw@host/db") == "postgresql+psycopg://user:pw@host/db"
    )
    assert (
        normalize_database_url("postgresql://user:pw@host/db")
        == "postgresql+psycopg://user:pw@host/db"
    )
    assert normalize_database_url("sqlite:///./memorycue.db") == "sqlite:///./memorycue.db"


@pytest.mark.parametrize(
    ("question", "answer", "source_id"),
    [
        ("What was I doing at 10 AM?", "At 10:00 AM, you were making tea.", "memory:1"),
        ("What was I doing at 10:12?", "At 10:10 AM, you were reading.", "memory:2"),
        ("what was i doing at 10:30 a.m. today", "At 10:25 AM, you were preparing to leave.", "memory:4"),
    ],
)
def test_activity_at_a_clock_time_uses_the_moment_in_progress(
    client: TestClient, question: str, answer: str, source_id: str
) -> None:
    seed(client)
    body = client.post("/api/query", json={"question": question}).json()
    assert body["intent"] == "recent_activity"
    assert body["answer"] == answer
    assert body["source_ids"] == [source_id]


@pytest.mark.parametrize(
    "question",
    ["What was I doing at 9 AM?", "What was I doing at 11:30 AM?", "What was I doing at 25:00?"],
)
def test_activity_at_a_clock_time_without_a_saved_moment_is_unknown(
    client: TestClient, question: str
) -> None:
    seed(client)
    body = client.post("/api/query", json={"question": question}).json()
    assert body["intent"] == "unknown"
    assert body["evidence"] == []


def test_activity_at_a_clock_time_answers_in_arabic(client: TestClient) -> None:
    seed(client)
    body = client.post(
        "/api/query",
        json={"question": "ماذا كنت أفعل الساعة 10 صباحًا؟", "language": "ar"},
    ).json()
    assert body["intent"] == "recent_activity"
    assert body["answer"] == "الساعة 10:00 صباحًا كنت: making tea."
    assert body["source_ids"] == ["memory:1"]


@pytest.mark.parametrize(
    ("question", "language", "answer", "source_id"),
    [
        ("what was I doing at ten AM", "en", "At 10:00 AM, you were making tea.", "memory:1"),
        ("what was I doing at ten twelve", "en", "At 10:10 AM, you were reading.", "memory:2"),
        ("what was I doing at half past ten a.m.", "en", "At 10:25 AM, you were preparing to leave.", "memory:4"),
        ("ماذا كنت افعل الساعة العاشرة صباحا", "ar", "الساعة 10:00 صباحًا كنت: making tea.", "memory:1"),
        ("ماذا كنت افعل الساعه العاشره والنصف", "ar", "الساعة 10:25 صباحًا كنت: preparing to leave.", "memory:4"),
    ],
)
def test_activity_at_a_spoken_clock_time_uses_the_moment_in_progress(
    client: TestClient, question: str, language: str, answer: str, source_id: str
) -> None:
    seed(client)
    body = client.post("/api/query", json={"question": question, "language": language}).json()
    assert body["intent"] == "recent_activity"
    assert body["answer"] == answer
    assert body["source_ids"] == [source_id]


@pytest.mark.parametrize(
    "question",
    [
        "what was I doing at nine AM",
        "what was I doing at eleven thirty",
        "ماذا كنت افعل الساعة التاسعة صباحا",
        "what was I doing at ten-ish o'clock",
        "ماذا كنت افعل الساعة الخامسة والعشرين",
    ],
)
def test_activity_at_an_unsupported_or_unresolved_spoken_time_is_unknown(
    client: TestClient, question: str
) -> None:
    seed(client)
    body = client.post("/api/query", json={"question": question}).json()
    assert body["intent"] == "unknown"
    assert body["source_ids"] == []
    assert body["evidence"] == []


@pytest.mark.parametrize("question", ["What was I doing?", "what was I doing at one point", "ماذا كنت افعل"])
def test_activity_questions_without_a_time_still_use_the_latest_moment(
    client: TestClient, question: str
) -> None:
    seed(client)
    latest = client.post("/api/query", json={"question": "what was I doing"}).json()
    body = client.post("/api/query", json={"question": question}).json()
    assert body["intent"] == "recent_activity"
    assert latest["source_ids"] and body["source_ids"] == latest["source_ids"]


@pytest.mark.parametrize(
    "question",
    [
        "What did my doctor say?",
        "What did I eat for lunch?",
        "What did Sara tell me?",
        "What was that?",
        "What did my doctor say at 10 AM?",
        "What was the weather at ten fifteen?",
    ],
)
def test_past_tense_questions_about_other_things_do_not_answer_with_an_activity(
    client: TestClient, question: str
) -> None:
    seed(client)
    body = client.post("/api/query", json={"question": question}).json()
    assert body["intent"] == "unknown"
    assert body["source_ids"] == []
    assert body["evidence"] == []


def test_database_media_storage_keeps_photos_without_local_files(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setenv("MEDIA_STORAGE", "database")
    seed(client)
    response = upload_memory(
        client,
        timestamp=timestamp_at(),
        location="Kitchen counter",
        description="I left my keys on the kitchen counter.",
    )
    assert response.status_code == 201
    image_url = response.json()["image_url"]

    media_directory = Path(os.environ["MEDIA_DIR"])
    assert not media_directory.exists() or not list(media_directory.iterdir())
    media_response = client.get(image_url)
    assert media_response.status_code == 200
    assert media_response.content == b"fake-image-content"
    assert media_response.headers["content-type"] == "image/jpeg"
    assert client.get(image_url, headers={USER_ID_HEADER: "2"}).status_code == 404

    seed(client)
    assert client.get(image_url).status_code == 404


def test_gemini_provider_is_selected_from_configuration(monkeypatch) -> None:
    monkeypatch.setenv("VISION_PROVIDER", "Gemini")
    monkeypatch.setenv("VISION_MODEL", "gemini-test")
    monkeypatch.setenv("VISION_API_KEY", "test-key")
    assert isinstance(vision_provider.get_vision_analyzer(), vision_provider.GeminiVisionAnalyzer)


def test_gemini_analyzer_sends_inline_image_and_parses_json(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["key"] = request.headers["x-goog-api-key"]
        captured["payload"] = json.loads(request.content)
        analysis = {
            "description": "Keys on a table.",
            "location": "Table",
            "activity": None,
            "objects": [{"name": "keys", "location": "table", "confidence": 0.9}],
        }
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps(analysis)}]}}]},
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        vision_provider.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    analyzer = vision_provider.GeminiVisionAnalyzer(api_key="test-key", model="gemini-test")
    result = asyncio.run(analyzer.analyze_image(b"img", "photo.png", context="kitchen"))

    assert result.location == "Table"
    assert result.objects[0].name == "keys"
    assert captured["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"
    )
    assert captured["key"] == "test-key"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    image_part = payload["contents"][0]["parts"][1]["inlineData"]
    assert image_part == {"mimeType": "image/png", "data": "aW1n"}
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert "kitchen" in payload["contents"][0]["parts"][0]["text"]


def test_gemini_analyzer_reports_a_rejected_request(monkeypatch) -> None:
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        vision_provider.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(lambda _request: httpx.Response(429)), **kwargs
        ),
    )
    analyzer = vision_provider.GeminiVisionAnalyzer(api_key="test-key", model="gemini-test")
    with pytest.raises(VisionProviderError):
        asyncio.run(analyzer.analyze_image(b"img", "photo.jpg"))
