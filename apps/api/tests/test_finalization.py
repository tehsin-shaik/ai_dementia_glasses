"""Regression tests for the prototype finalization pass."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.face import provider as face_provider
from app.face.service import MatchCandidate, choose_match
from app.vision import VisionAnalysis
from app.vision.schemas import normalize_analysis

from .test_api import (
    JPEG_SIGNATURE,
    StubFaceRecognizer,
    caregiver_headers,
    clear_schedule,
    client,  # noqa: F401 - pytest fixture
    recognize_face,
    seed,
    upload_face,
    user_headers,
)


UNKNOWN_EN = "I couldn't find matching saved information for that."


def ask(client: TestClient, question: str, language: str = "en") -> dict:
    response = client.post("/api/query", json={"question": question, "language": language})
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("What was I doing?", "recent_activity"),
        ("What did I do?", "recent_activity"),
        ("What did I do at 10 AM?", "time_anchored_activity"),
        ("What was I doing at 10 AM?", "time_anchored_activity"),
        ("Where are my keys?", "object_location"),
        ("Where did I leave my keys?", "object_location"),
        ("Who is Sarah?", "person_lookup"),
        ("What am I doing today?", "schedule"),
        ("What did I do today?", "today_recall"),
    ],
)
def test_required_questions_route_to_their_intent(client: TestClient, question: str, intent: str) -> None:
    seed(client)
    body = ask(client, question)
    assert body["intent"] == intent
    assert body["source_ids"]


@pytest.mark.parametrize(
    ("question", "language"),
    [
        ("What did my doctor say?", "en"),
        ("Where is Sarah's bag?", "en"),
        ("Did I take my medicine?", "en"),
        ("Did I take my medicine today?", "en"),
        ("What was I supposed to do?", "en"),
        ("What should I do now?", "en"),
        ("What do I do next?", "en"),
        ("Who is this?", "en"),
        ("هل أخذت دوائي اليوم؟", "ar"),
    ],
)
def test_adversarial_questions_are_unknown_with_no_sources(
    client: TestClient, question: str, language: str
) -> None:
    seed(client)
    body = ask(client, question, language)
    assert body["intent"] == "unknown"
    assert body["source_ids"] == []
    assert body["evidence"] == []


def test_activity_answers_state_when_the_moment_was_saved(client: TestClient) -> None:
    seed(client)
    latest = ask(client, "What was I doing?")
    timed = ask(client, "What was I doing at 10:12?")
    arabic = ask(client, "ماذا كنت أفعل؟", "ar")

    assert latest["answer"] == "Your last saved moment, at 10:25 AM: preparing to leave."
    assert timed["answer"] == "The closest saved moment before 10:12 AM was at 10:10 AM: reading."
    assert "10:25" in arabic["answer"]
    for body in (latest, timed, arabic):
        assert "you were keys" not in body["answer"].casefold()


def test_object_answers_say_last_recorded_not_currently(client: TestClient) -> None:
    seed(client)
    body = ask(client, "Where are my keys?")
    assert body["answer"].startswith("Last recorded:")
    assert "10:18 AM" in body["answer"]
    assert "are on" not in body["answer"]


@pytest.mark.parametrize(
    ("filename", "content", "content_type"),
    [
        ("memory.jpg", b"not-an-image", "image/jpeg"),
        ("memory.png", JPEG_SIGNATURE + b"jpeg-bytes", "image/png"),
        ("memory.webp", b"RIFF0000WAVE", "image/webp"),
    ],
)
def test_uploads_whose_bytes_do_not_match_their_type_are_rejected(
    client: TestClient, filename: str, content: bytes, content_type: str
) -> None:
    seed(client)
    response = client.post(
        "/api/memories",
        files={"image": (filename, content, content_type)},
        data={"timestamp": "2026-01-01T10:00:00", "location": "Kitchen", "description": "A cup."},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "The file is not a valid image of its stated type."}


@pytest.mark.parametrize(
    ("filename", "content", "content_type"),
    [
        ("memory.png", b"\x89PNG\r\n\x1a\nrest", "image/png"),
        ("memory.webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
    ],
)
def test_uploads_with_a_matching_signature_are_accepted(
    client: TestClient, filename: str, content: bytes, content_type: str
) -> None:
    seed(client)
    response = client.post(
        "/api/memories",
        files={"image": (filename, content, content_type)},
        data={"timestamp": "2026-01-01T10:00:00", "location": "Kitchen", "description": "A cup."},
    )
    assert response.status_code == 201


def test_vision_normalization_drops_weak_and_duplicate_objects() -> None:
    analysis = VisionAnalysis(
        description="  Keys and a mug on a counter. ",
        location="  ",
        activity=None,
        objects=[
            {"name": "mug", "location": "counter", "confidence": 0.7},
            {"name": "Keys", "location": "counter", "confidence": 0.95},
            {"name": "keys", "location": "floor", "confidence": 0.5},
            {"name": "wallet", "location": "counter", "confidence": 0.2},
            {"name": " ", "location": "counter", "confidence": 0.9},
        ],
    )

    normalized = normalize_analysis(analysis)

    assert normalized.description == "Keys and a mug on a counter."
    assert normalized.location is None
    assert [(item.name, item.location) for item in normalized.objects] == [
        ("Keys", "counter"),
        ("mug", "counter"),
    ]


class _ScoreTable:
    def __init__(self, scores: dict[tuple[float, ...], float]) -> None:
        self.scores = scores

    def compare(self, query: list[float], reference: list[float]) -> float:
        return self.scores[tuple(reference)]


def test_several_photos_of_one_person_are_not_ambiguous_with_each_other() -> None:
    recognizer = _ScoreTable({(1.0,): 0.9, (2.0,): 0.88, (3.0,): 0.3})
    decision = choose_match(
        [0.0],
        [MatchCandidate(1, [1.0]), MatchCandidate(1, [2.0]), MatchCandidate(2, [3.0])],
        recognizer,  # type: ignore[arg-type]
    )
    assert decision.person_id == 1
    assert decision.outcome == "matched"
    assert decision.second_score == 0.3


def test_close_scores_for_different_people_are_ambiguous() -> None:
    recognizer = _ScoreTable({(1.0,): 0.9, (2.0,): 0.86})
    decision = choose_match(
        [0.0], [MatchCandidate(1, [1.0]), MatchCandidate(2, [2.0])], recognizer  # type: ignore[arg-type]
    )
    assert decision.person_id is None
    assert decision.outcome == "ambiguous"


@pytest.mark.parametrize(
    ("camera", "outcome"),
    [(b"no-face", "no_face"), (b"multiple-faces", "multiple_faces"), (b"weak-camera", "low_confidence")],
)
def test_face_unknown_reports_why(client: TestClient, monkeypatch, camera: bytes, outcome: str) -> None:
    seed(client)
    monkeypatch.setattr(face_provider, "get_face_recognizer", lambda: StubFaceRecognizer())
    sarah = client.get("/api/caregiver/patients/1/people", headers=caregiver_headers(1)).json()[0]
    upload_face(client, patient_id=1, person_id=sarah["id"], caregiver_id=1, image_bytes=b"sarah-reference")

    body = recognize_face(client, user_id=1, image_bytes=camera).json()

    assert body["recognized"] is False
    assert body["name"] is None
    assert body["outcome"] == outcome
    assert body["diagnostics"] is None


def test_face_without_enrollment_reports_no_enrollment(client: TestClient, monkeypatch) -> None:
    seed(client)
    monkeypatch.setattr(face_provider, "get_face_recognizer", lambda: StubFaceRecognizer())
    body = recognize_face(client, user_id=1, image_bytes=b"sarah-camera").json()
    assert body["recognized"] is False
    assert body["outcome"] == "no_enrollment"


def test_face_diagnostics_are_opt_in_and_never_expose_embeddings(client: TestClient, monkeypatch) -> None:
    seed(client)
    monkeypatch.setattr(face_provider, "get_face_recognizer", lambda: StubFaceRecognizer())
    sarah = client.get("/api/caregiver/patients/1/people", headers=caregiver_headers(1)).json()[0]
    upload_face(client, patient_id=1, person_id=sarah["id"], caregiver_id=1, image_bytes=b"sarah-reference")

    response = client.post(
        "/api/face/recognize?diagnostics=true",
        files={"image": ("camera.jpg", JPEG_SIGNATURE + b"weak-camera", "image/jpeg")},
        headers=user_headers(1),
    )

    body = response.json()
    assert body["recognized"] is False
    assert body["diagnostics"]["best_score"] == pytest.approx(0.4)
    assert body["diagnostics"]["threshold"] == 0.65
    assert "embedding" not in response.text


def test_a_person_seen_again_is_not_recued_during_the_cooldown(client: TestClient, monkeypatch) -> None:
    seed(client)
    clear_schedule(client, 1)
    monkeypatch.setenv("CUE_OBJECT_LOOKBACK_MINUTES", "0")
    monkeypatch.setattr(face_provider, "get_face_recognizer", lambda: StubFaceRecognizer())
    sarah = client.get("/api/caregiver/patients/1/people", headers=caregiver_headers(1)).json()[0]
    upload_face(client, patient_id=1, person_id=sarah["id"], caregiver_id=1, image_bytes=b"sarah-reference")

    assert recognize_face(client, user_id=1, image_bytes=b"sarah-camera").json()["recognized"]
    first = client.get("/api/cues", headers=user_headers(1)).json()["cues"]
    assert [cue["type"] for cue in first] == ["recognized_person"]
    presented = client.post(
        "/api/cues/present",
        headers=user_headers(1),
        json={"cue_id": first[0]["id"], "presentation_id": "00000000-0000-4000-8000-0000000000aa"},
    )
    assert presented.status_code == 200

    assert recognize_face(client, user_id=1, image_bytes=b"sarah-camera").json()["recognized"]
    again = client.get("/api/cues", headers=user_headers(1)).json()["cues"]

    assert again == []
