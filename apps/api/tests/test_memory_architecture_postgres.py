"""Postgres-specific checks for the observation hierarchy.

Skipped unless MEMORYCUE_TEST_POSTGRES_URL points at a disposable database,
for example: docker run -e POSTGRES_PASSWORD=pw -p 55432:5432 postgres:16 and
MEMORYCUE_TEST_POSTGRES_URL=postgresql://postgres:pw@localhost:55432/postgres
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
import os

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, advisory_lock, create_database_engine
from app.episode_service import consolidate_episodes, consolidate_in_background
from app.memory_service import save_reviewed_moment
from app.migrations import run_migrations
from app.models import Episode, EpisodeEvent, Event, MediaBlob, Memory, Observation, User
from app.observation_service import ObservationInput, create_observation
from app.query_service import answer_question
from app.retention_service import cleanup_abandoned_observations
from app.seed import seed_demo_data

POSTGRES_URL = os.getenv("MEMORYCUE_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="MEMORYCUE_TEST_POSTGRES_URL is not set")
LEGACY_TABLES = {"memories", "memory_observations", "memory_events", "memory_corrections", "object_observations"}


def at(hour: int, minute: int = 0) -> datetime:
    return datetime.combine(date.today(), time(hour, minute))


@pytest.fixture
def engine():
    engine = create_database_engine(POSTGRES_URL)
    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS memories CASCADE"))
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_hierarchy_json_and_grouping_queries_work_on_postgres(engine, session_factory) -> None:
    Base.metadata.create_all(engine)
    with session_factory() as db:
        seed_demo_data(db)
        user_id = db.scalar(select(User.id).order_by(User.id))
        create_observation(
            db,
            user_id,
            ObservationInput(
                timestamp=at(10, 20),
                source="meta_glasses",
                location_label="Kitchen",
                objects=[{"name": "Wallet", "location": "counter", "confidence": 0.9}],
                metadata={"device": {"battery": 0.5}},
            ),
        )
        db.commit()
        consolidate_episodes(db, user_id)
        db.commit()
        assert consolidate_episodes(db, user_id) == []

        observation = db.scalar(select(Observation).where(Observation.source == "meta_glasses"))
        assert observation.detected_objects == [{"name": "wallet", "location": "counter", "confidence": 0.9}]
        assert observation.extra == {"device": {"battery": 0.5}}
        assert db.scalar(select(func.count()).select_from(Event).where(Event.id.not_in(select(EpisodeEvent.event_id)))) == 0
        assert "kitchen counter" in answer_question(db, user_id, "Where are my keys?").answer
        assert answer_question(db, user_id, "Where is my wallet?").intent == "unknown"


def test_failed_event_inference_rolls_back_only_its_savepoint(engine, session_factory, monkeypatch) -> None:
    Base.metadata.create_all(engine)

    def partial_then_crash(db: Session, observation: Observation) -> list[Event]:
        db.add(Event(user_id=observation.user_id, start_time=observation.timestamp, event_type="x", title="partial", confidence=0.1, inference="rule:x"))
        db.flush()
        raise RuntimeError("rule crashed")

    monkeypatch.setattr("app.observation_service.events_for_observation", partial_then_crash)
    with session_factory() as db:
        user = User(name="Alex")
        db.add(user)
        db.flush()
        observation = create_observation(db, user.id, ObservationInput(timestamp=at(9), description="Kept."))
        db.commit()
        assert db.get(Observation, observation.id).description == "Kept."
        assert db.scalar(select(func.count()).select_from(Event)) == 0


def test_concurrent_consolidation_assigns_each_event_once(engine, session_factory) -> None:
    Base.metadata.create_all(engine)
    with session_factory() as db:
        user = User(name="Alex")
        db.add(user)
        db.flush()
        for minute in range(0, 60, 5):
            save_reviewed_moment(db, user.id, timestamp=at(9, minute), location="Kitchen", description=f"Moment {minute}.")
        db.commit()
        user_id = user.id

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: consolidate_in_background(engine, user_id), range(4)))

    with session_factory() as db:
        event_count = db.scalar(select(func.count()).select_from(Event))
        assert db.scalar(select(func.count()).select_from(EpisodeEvent)) == event_count
        assert db.scalar(select(func.count(func.distinct(EpisodeEvent.event_id)))) == event_count
        assert db.scalar(select(func.count()).select_from(Episode)) == 1


def test_advisory_lock_survives_commits_inside_the_block(engine, session_factory) -> None:
    Base.metadata.create_all(engine)
    with session_factory() as db, advisory_lock(db, 4242):
        db.add(User(name="Alex"))
        db.commit()
        with engine.connect() as other:
            assert other.execute(text("SELECT pg_try_advisory_lock(4242)")).scalar() is False


def test_legacy_migration_runs_concurrently_and_repeatedly(engine, session_factory) -> None:
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name not in LEGACY_TABLES])
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE memories (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), "
            "timestamp TIMESTAMP NOT NULL, location VARCHAR(120) NOT NULL, activity VARCHAR(200), "
            "description TEXT NOT NULL)"
        ))
        connection.execute(text("INSERT INTO users (id, name) VALUES (1, 'Alex')"))
        connection.execute(
            text("INSERT INTO memories (id, user_id, timestamp, location, activity, description) VALUES "
                 "(7, 1, :a, 'Kitchen', 'making tea', 'Alex was making tea.'), (9, 1, :b, 'Kitchen', NULL, 'Keys on the counter.')"),
            {"a": at(10), "b": at(10, 18)},
        )
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO object_observations (user_id, object_name, location, observed_at, memory_id) VALUES (1, 'keys', 'kitchen counter', :b, 9)"),
            {"b": at(10, 18)},
        )

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: run_migrations(engine, session_factory), range(3)))
    assert sorted(results) == [0, 0, 2]
    assert run_migrations(engine, session_factory) == 0

    assert {"episode_id", "people", "objects"} <= {column["name"] for column in inspect(engine).get_columns("memories")}
    with session_factory() as db:
        assert sorted(db.scalars(select(Memory.id))) == [7, 9]
        assert db.scalar(select(func.count()).select_from(Observation)) == 2
        assert {row.extra["original_source"] for row in db.scalars(select(Observation))} == {"unknown"}
        assert all(memory.episode_id is not None for memory in db.scalars(select(Memory)))
        assert "kitchen counter" in answer_question(db, 1, "Where are my keys?").answer


def _abandoned_capture(db: Session, user_id: int, filename: str, hour: int = 9) -> Observation:
    db.add(MediaBlob(filename=filename, user_id=user_id, content_type="image/jpeg", data=b"frame"))
    observation = create_observation(
        db,
        user_id,
        ObservationInput(
            timestamp=at(hour),
            source="browser_camera",
            image_path=filename,
            objects=[{"name": "umbrella", "location": "hall", "confidence": 0.9}],
        ),
    )
    observation.created_at = datetime.now() - timedelta(days=30)
    return observation


def test_concurrent_cleanup_deletes_each_capture_and_photo_once(engine, session_factory) -> None:
    Base.metadata.create_all(engine)
    with session_factory() as db:
        user = User(name="Alex")
        db.add(user)
        db.flush()
        doomed = _abandoned_capture(db, user.id, "a" * 32 + ".jpg", hour=15)
        source = _abandoned_capture(db, user.id, "b" * 32 + ".jpg")
        create_observation(
            db,
            user.id,
            ObservationInput(timestamp=at(9), description="Reviewed.", reviewed=True, metadata={"reviewed_from_observation_id": source.id}),
        )
        db.commit()
        consolidate_episodes(db, user.id)
        db.commit()
        user_id, doomed_id, source_id = user.id, doomed.id, source.id

    def run(_: int):
        with session_factory() as db:
            return cleanup_abandoned_observations(db, user_id)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, range(4)))

    assert sorted(len(result.deleted_observation_ids) for result in results) == [0, 0, 0, 1]
    assert sum(len(result.deleted_media) for result in results) == 1
    assert all(result.errors == [] for result in results)
    with session_factory() as db:
        assert db.get(Observation, doomed_id) is None
        assert db.get(Observation, source_id) is not None
        assert db.get(MediaBlob, "a" * 32 + ".jpg") is None
        assert db.get(MediaBlob, "b" * 32 + ".jpg") is not None
        orphaned = select(func.count()).select_from(EpisodeEvent).where(EpisodeEvent.event_id.not_in(select(Event.id)))
        assert db.scalar(orphaned) == 0


def test_cleanup_skips_a_capture_that_is_being_saved(engine, session_factory) -> None:
    Base.metadata.create_all(engine)
    with session_factory() as db:
        user = User(name="Alex")
        db.add(user)
        db.flush()
        capture = _abandoned_capture(db, user.id, "c" * 32 + ".jpg")
        db.commit()
        user_id, capture_id = user.id, capture.id

    with session_factory() as saving:
        saving.scalar(select(Observation).where(Observation.id == capture_id).with_for_update())
        with session_factory() as db:
            result = cleanup_abandoned_observations(db, user_id)
        assert (result.examined, result.deleted_observation_ids) == (0, [])
        saving.rollback()

    with session_factory() as db:
        assert db.get(Observation, capture_id) is not None
        assert cleanup_abandoned_observations(db, user_id).deleted_observation_ids == [capture_id]
