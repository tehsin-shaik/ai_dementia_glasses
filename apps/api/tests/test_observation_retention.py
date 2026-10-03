"""Retention of abandoned, unreviewed captures."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.episode_service import consolidate_episodes
from app.identity import USER_ID_HEADER
from app.media_storage import configured_media_directory, new_media_filename, write_media_file
from app.memory_service import save_reviewed_moment
from app.models import (
    Episode,
    EpisodeEvent,
    EpisodeObservation,
    Event,
    EventObservation,
    MediaBlob,
    Memory,
    MemoryEvent,
    Observation,
)
from app.observation_service import ObservationInput, create_observation
from app.retention_service import RetentionConfigError, cleanup_abandoned_observations, observation_retention
from tests.test_memory_architecture import at, client, db, engine, make_user, seed, session_factory  # noqa: F401

ABANDONED = 200
RECENT = 2


def capture(db: Session, user_id: int, *, hours_old: int = ABANDONED, image: str | None = None, **fields) -> Observation:
    fields.setdefault("timestamp", at(9))
    observation = create_observation(db, user_id, ObservationInput(source="browser_camera", image_path=image, **fields))
    observation.created_at = datetime.now() - timedelta(hours=hours_old)
    db.commit()
    return observation


def photo(data: bytes = b"captured-frame") -> str:
    filename = new_media_filename(".jpg")
    write_media_file(filename, data)
    return filename


def on_disk(filename: str) -> bool:
    return (configured_media_directory() / filename).is_file()


def exists(db: Session, model, ident: int) -> bool:
    db.expire_all()
    return db.get(model, ident) is not None


def count(db: Session, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def held_object(name: str = "umbrella") -> list[dict]:
    return [{"name": name, "location": "hall", "confidence": 0.9}]


# Retention


def test_an_old_unreviewed_capture_and_its_photo_are_deleted(db: Session) -> None:
    user = make_user(db)
    filename = photo()
    old = capture(db, user.id, image=filename)

    result = cleanup_abandoned_observations(db, user.id)

    assert result.deleted_observation_ids == [old.id]
    assert result.deleted_media == [filename]
    assert (result.examined, result.retained, result.errors) == (1, 0, [])
    assert not exists(db, Observation, old.id)
    assert not on_disk(filename)


def test_a_recent_unreviewed_capture_is_kept(db: Session) -> None:
    user = make_user(db)
    filename = photo()
    recent = capture(db, user.id, hours_old=RECENT, image=filename)

    result = cleanup_abandoned_observations(db, user.id)

    assert result.examined == 0
    assert exists(db, Observation, recent.id)
    assert on_disk(filename)


def test_the_retention_period_is_configurable(db: Session, monkeypatch) -> None:
    user = make_user(db)
    seventy_two = capture(db, user.id, hours_old=72)
    thirty = capture(db, user.id, hours_old=30)

    assert observation_retention() == timedelta(hours=168)
    assert cleanup_abandoned_observations(db, user.id).deleted_observation_ids == []

    monkeypatch.setenv("OBSERVATION_RETENTION_HOURS", "48")
    assert observation_retention() == timedelta(hours=48)
    assert cleanup_abandoned_observations(db, user.id).deleted_observation_ids == [seventy_two.id]
    assert exists(db, Observation, thirty.id)


@pytest.mark.parametrize("value", ["abc", "1.5", "0", "-5", "23"])
def test_an_invalid_retention_period_deletes_nothing(db: Session, monkeypatch, value: str) -> None:
    user = make_user(db)
    old = capture(db, user.id)
    monkeypatch.setenv("OBSERVATION_RETENTION_HOURS", value)

    with pytest.raises(RetentionConfigError):
        cleanup_abandoned_observations(db, user.id)
    assert exists(db, Observation, old.id)


def test_a_capture_without_an_ingest_time_is_kept(db: Session) -> None:
    user = make_user(db)
    unknown_age = capture(db, user.id)
    unknown_age.created_at = None
    db.commit()

    assert cleanup_abandoned_observations(db, user.id).examined == 0
    assert exists(db, Observation, unknown_age.id)


# Safety


def test_reviewed_observations_are_never_deleted(db: Session) -> None:
    user = make_user(db)
    filename = photo()
    saved = save_reviewed_moment(db, user.id, timestamp=at(9), location="Hall", description="Coat on the hook.", image_path=filename)
    saved.observation.created_at = datetime.now() - timedelta(days=365)
    db.commit()

    assert cleanup_abandoned_observations(db, user.id).examined == 0
    assert exists(db, Observation, saved.observation.id)
    assert all(exists(db, Event, event.id) for event in saved.events)
    assert on_disk(filename)


def test_a_capture_saved_as_a_memory_and_its_shared_photo_are_kept(client: TestClient, db: Session) -> None:
    seed(client)
    raw = client.post(
        "/api/observations",
        files={"image": ("glasses-capture.jpg", b"captured-frame", "image/jpeg")},
        data={"timestamp": at(9).isoformat(), "source": "browser_camera", "analyze": "false"},
    ).json()
    saved = client.post(
        "/api/memories",
        data={"observation_id": str(raw["id"]), "timestamp": at(9).isoformat(), "location": "Hall", "description": "Coat."},
    ).json()
    db.get(Observation, raw["id"]).created_at = datetime.now() - timedelta(hours=ABANDONED)
    db.commit()

    result = cleanup_abandoned_observations(db, 1)

    assert (result.examined, result.retained, result.deleted_media) == (1, 1, [])
    assert exists(db, Observation, raw["id"])
    assert client.get(saved["image_url"]).content == b"captured-frame"


def test_the_source_of_a_reviewed_observation_is_kept(db: Session) -> None:
    user = make_user(db)
    filename = photo()
    raw = capture(db, user.id, image=filename)
    create_observation(
        db,
        user.id,
        ObservationInput(
            timestamp=at(9),
            description="Reviewed copy.",
            reviewed=True,
            metadata={"reviewed_from_observation_id": raw.id},
        ),
    )
    db.commit()

    assert cleanup_abandoned_observations(db, user.id).retained == 1
    assert exists(db, Observation, raw.id)
    assert on_disk(filename)


def test_an_event_shared_with_a_kept_capture_keeps_both(db: Session) -> None:
    user = make_user(db)
    kitchen = capture(db, user.id, timestamp=at(10), location_label="Kitchen")
    hallway = capture(db, user.id, hours_old=RECENT, timestamp=at(10, 10), location_label="Hallway")
    shared = db.scalar(select(EventObservation.event_id).where(EventObservation.observation_id == hallway.id))
    assert shared is not None

    assert cleanup_abandoned_observations(db, user.id).retained == 1
    assert exists(db, Observation, kitchen.id) and exists(db, Event, shared)

    hallway.created_at = datetime.now() - timedelta(hours=ABANDONED)
    db.commit()
    result = cleanup_abandoned_observations(db, user.id)
    assert sorted(result.deleted_observation_ids) == sorted([kitchen.id, hallway.id])
    assert result.deleted_events == 1
    assert count(db, Event) == 0 and count(db, EventObservation) == 0


def test_an_event_linked_to_a_memory_keeps_its_capture(db: Session) -> None:
    user = make_user(db)
    raw = capture(db, user.id, objects=held_object())
    event_id = db.scalar(select(EventObservation.event_id).where(EventObservation.observation_id == raw.id))
    saved = save_reviewed_moment(db, user.id, timestamp=at(12), location="Hall", description="Umbrella.")
    db.add(MemoryEvent(memory_id=saved.memory.id, event_id=event_id))
    db.commit()

    assert cleanup_abandoned_observations(db, user.id).retained == 1
    assert exists(db, Observation, raw.id) and exists(db, Event, event_id)


def test_an_episode_with_reviewed_events_keeps_the_capture_and_is_unchanged(db: Session) -> None:
    user = make_user(db)
    saved = save_reviewed_moment(db, user.id, timestamp=at(10), location="Hall", description="Coat on the hook.")
    raw = capture(db, user.id, timestamp=at(10, 5), objects=held_object())
    consolidate_episodes(db, user.id)
    db.commit()
    episode = db.scalar(select(Episode))
    before = (episode.title, episode.summary, episode.start_time, episode.end_time, count(db, EpisodeEvent))
    assert db.scalar(select(func.count()).select_from(Episode)) == 1

    assert cleanup_abandoned_observations(db, user.id).retained == 1

    db.expire_all()
    episode = db.get(Episode, episode.id)
    assert (episode.title, episode.summary, episode.start_time, episode.end_time, count(db, EpisodeEvent)) == before
    assert exists(db, Observation, raw.id)
    assert db.get(Memory, saved.memory.id).episode_id == episode.id


def test_a_wholly_abandoned_episode_is_deleted_with_its_events(db: Session) -> None:
    user = make_user(db)
    raw = capture(db, user.id, timestamp=at(15), objects=held_object())
    consolidate_episodes(db, user.id)
    db.commit()
    assert count(db, Episode) == 1 and count(db, EpisodeObservation) == 1

    result = cleanup_abandoned_observations(db, user.id)

    assert (result.deleted_observation_ids, result.deleted_events, result.deleted_episodes) == ([raw.id], 1, 1)
    for model in (Episode, EpisodeEvent, EpisodeObservation, Event, EventObservation, Observation):
        assert count(db, model) == 0


def test_an_episode_referenced_by_a_memory_is_kept(db: Session) -> None:
    user = make_user(db)
    raw = capture(db, user.id, timestamp=at(15), objects=held_object())
    consolidate_episodes(db, user.id)
    saved = save_reviewed_moment(db, user.id, timestamp=at(18), location="Hall", description="Elsewhere.")
    saved.memory.episode_id = db.scalar(select(Episode.id))
    db.commit()

    assert cleanup_abandoned_observations(db, user.id).retained == 1
    assert exists(db, Observation, raw.id)


# Media


def test_a_photo_shared_with_a_kept_capture_is_kept(db: Session) -> None:
    user = make_user(db)
    filename = photo()
    old = capture(db, user.id, image=filename)
    capture(db, user.id, hours_old=RECENT, image=filename)

    result = cleanup_abandoned_observations(db, user.id)

    assert result.deleted_observation_ids == [old.id]
    assert result.retained_media == [filename] and result.deleted_media == []
    assert on_disk(filename)


def test_a_photo_referenced_by_a_memory_is_kept(db: Session) -> None:
    user = make_user(db)
    filename = photo()
    old = capture(db, user.id, image=filename)
    save_reviewed_moment(db, user.id, timestamp=at(12), location="Hall", description="Same photo.", image_path=filename)
    db.commit()

    result = cleanup_abandoned_observations(db, user.id)

    assert result.deleted_observation_ids == [old.id]
    assert result.retained_media == [filename]
    assert on_disk(filename)


def test_database_media_is_deleted_only_when_unreferenced(client: TestClient, db: Session, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_STORAGE", "database")
    seed(client)
    upload = {"image": ("glasses-capture.jpg", b"captured-frame", "image/jpeg")}
    form = {"timestamp": at(9).isoformat(), "source": "browser_camera", "analyze": "false"}
    abandoned = client.post("/api/observations", files=upload, data=form).json()
    kept = client.post("/api/observations", files=upload, data=form).json()
    client.post(
        "/api/memories",
        data={"observation_id": str(kept["id"]), "timestamp": at(9).isoformat(), "location": "Hall", "description": "Coat."},
    )
    for observation_id in (abandoned["id"], kept["id"]):
        db.get(Observation, observation_id).created_at = datetime.now() - timedelta(hours=ABANDONED)
    db.commit()
    abandoned_file = abandoned["image_url"].removeprefix("/api/media/")
    kept_file = kept["image_url"].removeprefix("/api/media/")

    result = cleanup_abandoned_observations(db, 1)

    assert result.deleted_observation_ids == [abandoned["id"]]
    assert result.deleted_media == [abandoned_file]
    assert not exists_blob(db, abandoned_file) and exists_blob(db, kept_file)
    assert client.get(abandoned["image_url"]).status_code == 404
    assert client.get(kept["image_url"]).content == b"captured-frame"


def exists_blob(db: Session, filename: str) -> bool:
    db.expire_all()
    return db.get(MediaBlob, filename) is not None


def test_a_missing_photo_file_is_not_an_error(db: Session) -> None:
    user = make_user(db)
    old = capture(db, user.id, image=new_media_filename(".jpg"))

    result = cleanup_abandoned_observations(db, user.id)

    assert result.deleted_observation_ids == [old.id]
    assert result.errors == []


# Isolation


def test_cleanup_never_crosses_users(db: Session) -> None:
    alex, jordan = make_user(db, "Alex"), make_user(db, "Jordan")
    jordan_photo = photo()
    jordan_capture = capture(db, jordan.id, image=jordan_photo)
    shared = photo()
    alex_capture = capture(db, alex.id, image=shared)
    save_reviewed_moment(db, jordan.id, timestamp=at(12), location="Hall", description="Jordan's.", image_path=shared)
    blob_name = new_media_filename(".jpg")
    db.add(MediaBlob(filename=blob_name, user_id=jordan.id, content_type="image/jpeg", data=b"jordan"))
    alex_blob_ref = capture(db, alex.id, image=blob_name)

    result = cleanup_abandoned_observations(db, alex.id)

    assert sorted(result.deleted_observation_ids) == sorted([alex_capture.id, alex_blob_ref.id])
    assert sorted(result.retained_media) == sorted([shared, blob_name])
    assert exists(db, Observation, jordan_capture.id) and on_disk(jordan_photo) and on_disk(shared)
    assert exists_blob(db, blob_name)


# Reliability


def test_cleanup_is_idempotent_and_safe_when_empty(db: Session) -> None:
    user = make_user(db)
    assert cleanup_abandoned_observations(db, user.id).examined == 0
    capture(db, user.id, image=photo(), objects=held_object())
    capture(db, user.id, hours_old=RECENT)

    first = cleanup_abandoned_observations(db, user.id)
    state = [count(db, model) for model in (Observation, Event, EventObservation, Episode, MediaBlob)]
    second = cleanup_abandoned_observations(db, user.id)

    assert len(first.deleted_observation_ids) == 1
    assert (second.examined, second.deleted_observation_ids, second.deleted_media, second.errors) == (0, [], [], [])
    assert [count(db, model) for model in (Observation, Event, EventObservation, Episode, MediaBlob)] == state


def test_a_partially_cleaned_capture_is_finished(db: Session) -> None:
    user = make_user(db)
    raw = capture(db, user.id, objects=held_object())
    event_id = db.scalar(select(EventObservation.event_id).where(EventObservation.observation_id == raw.id))
    db.query(EventObservation).filter(EventObservation.event_id == event_id).delete()
    db.query(Event).filter(Event.id == event_id).delete()
    db.commit()

    assert cleanup_abandoned_observations(db, user.id).deleted_observation_ids == [raw.id]


# Regression


def test_cleanup_leaves_answers_rewind_and_memories_unchanged(client: TestClient, db: Session) -> None:
    seed(client)
    response = client.post(
        "/api/observations",
        files={"image": ("keys-on-table.jpg", b"captured-frame", "image/jpeg")},
        data={"timestamp": at(11, 50).isoformat(), "source": "browser_camera"},
    )
    assert response.status_code == 201
    raw_id = response.json()["id"]
    assert client.post("/api/episodes/consolidate").status_code == 200

    def snapshot() -> list:
        questions = ["Where are my keys?", "What did I do today?", "What was I doing at 10 AM?", "Where is my passport?"]
        return [
            client.get("/api/memories").json(),
            client.get("/api/rewind").json(),
            [client.post("/api/query", json={"question": question}).json() for question in questions],
        ]

    before = snapshot()
    db.get(Observation, raw_id).created_at = datetime.now() - timedelta(hours=ABANDONED)
    db.commit()
    assert cleanup_abandoned_observations(db, 1).deleted_observation_ids == [raw_id]
    assert snapshot() == before


def test_a_new_capture_cleans_up_abandoned_ones_and_a_cleaned_capture_cannot_be_saved(client: TestClient, db: Session) -> None:
    seed(client)
    upload = {"image": ("glasses-capture.jpg", b"captured-frame", "image/jpeg")}
    form = {"timestamp": at(9).isoformat(), "source": "browser_camera", "analyze": "false"}
    old = client.post("/api/observations", files=upload, data=form).json()
    db.get(Observation, old["id"]).created_at = datetime.now() - timedelta(hours=ABANDONED)
    db.commit()
    other_user_old = client.post("/api/observations", files=upload, data=form, headers={USER_ID_HEADER: "2"}).json()
    db.get(Observation, other_user_old["id"]).created_at = datetime.now() - timedelta(hours=ABANDONED)
    db.commit()

    fresh = client.post("/api/observations", files=upload, data=form).json()

    assert not exists(db, Observation, old["id"])
    assert exists(db, Observation, fresh["id"]) and exists(db, Observation, other_user_old["id"])
    assert client.get(old["image_url"]).status_code == 404
    saved = client.post(
        "/api/memories",
        data={"observation_id": str(old["id"]), "timestamp": at(9).isoformat(), "location": "Hall", "description": "Too late."},
    )
    assert saved.status_code == 404
