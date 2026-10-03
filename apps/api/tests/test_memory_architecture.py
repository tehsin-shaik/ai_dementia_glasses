"""Tests for the Observation -> Event -> Episode -> Memory hierarchy."""

from collections.abc import Generator
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.correction_service import latest_correction
from app.database import Base, create_database_engine, get_db
from app.episode_service import consolidate_episodes
from app.event_service import generate_events
from app.identity import USER_ID_HEADER
from app.main import app
from app.memory_service import save_reviewed_moment
from app.memory_text import episode_to_text, event_to_text, memory_to_text, observation_to_text
from app.migrations import backfill_legacy_memories, run_migrations
from app.models import (
    Episode,
    EpisodeEvent,
    Event,
    EventObservation,
    Memory,
    MemoryEvent,
    MemoryObservation,
    ObjectObservation,
    Observation,
    Person,
    ScheduleItem,
    User,
)
from app.observation_service import (
    OBSERVATION_SOURCES,
    ObservationInput,
    ObservationValidationError,
    create_observation,
)
from app.query_service import answer_question
from app.rewind_service import PHOTO_ORIGINS, build_rewind


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    for name in ("VISION_PROVIDER", "VISION_MODEL", "VISION_API_KEY", "MEDIA_STORAGE"):
        monkeypatch.delenv(name, raising=False)
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture
def client(session_factory) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, headers={USER_ID_HEADER: "1"}) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def db(session_factory) -> Generator[Session, None, None]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def seed(client: TestClient) -> None:
    assert client.post("/api/demo/seed").status_code == 200


def make_user(db: Session, name: str = "Test") -> User:
    user = User(name=name)
    db.add(user)
    db.flush()
    return user


def at(hour: int, minute: int = 0) -> datetime:
    return datetime.combine(date.today(), time(hour, minute))


def observation_events(db: Session, observation_id: int) -> list[Event]:
    return list(
        db.scalars(
            select(Event)
            .join(EventObservation, EventObservation.event_id == Event.id)
            .where(EventObservation.observation_id == observation_id)
            .order_by(Event.id)
        )
    )


# --- Observation ---------------------------------------------------------------


def test_observation_without_image_location_people_or_objects_is_kept_without_events(db: Session) -> None:
    user = make_user(db)
    observation = create_observation(
        db, user.id, ObservationInput(timestamp=at(9), source="meta_glasses", transcript="  Hello there.  ")
    )
    db.commit()

    assert observation.id is not None
    assert observation.image_path is None
    assert observation.location_label is None
    assert observation.detected_people == []
    assert observation.detected_objects == []
    assert observation.transcript == "Hello there."
    assert observation.reviewed is False
    assert observation_events(db, observation.id) == []


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"source": "fax_machine"}, "Source must be one of"),
        ({"timestamp": datetime(1999, 12, 31)}, "outside the accepted range"),
        ({"timestamp": datetime.now() + timedelta(days=3)}, "outside the accepted range"),
        ({"latitude": 24.4}, "provided together"),
        ({"latitude": 124.0, "longitude": 54.0}, "Latitude must be between"),
    ],
)
def test_invalid_observations_are_rejected(db: Session, changes: dict, message: str) -> None:
    user = make_user(db)
    fields = {"timestamp": at(9), "source": "browser_camera", **changes}
    with pytest.raises(ObservationValidationError, match=message):
        create_observation(db, user.id, ObservationInput(**fields))


def test_observation_requires_an_existing_user(db: Session) -> None:
    with pytest.raises(ObservationValidationError, match="Unknown user"):
        create_observation(db, 999, ObservationInput(timestamp=at(9)))


def test_timezone_aware_timestamps_are_stored_as_naive_local_time(db: Session) -> None:
    user = make_user(db)
    aware = datetime.now().astimezone().replace(microsecond=0)
    observation = create_observation(db, user.id, ObservationInput(timestamp=aware))
    assert observation.timestamp.tzinfo is None
    assert observation.timestamp == aware.replace(tzinfo=None)


# --- Events ----------------------------------------------------------------------


def test_reviewed_moment_creates_events_memory_and_links(db: Session) -> None:
    user = make_user(db)
    saved = save_reviewed_moment(
        db,
        user.id,
        timestamp=at(10),
        location="Kitchen",
        description="Keys on the counter.",
        activity="Putting keys down",
        object_name="Keys",
        source="browser_camera",
    )
    db.commit()

    observation, memory = saved.observation, saved.memory
    assert observation.source == "browser_camera"
    assert observation.reviewed is True
    events = observation_events(db, observation.id)
    assert {event.event_type for event in events} == {"recorded_activity", "object_seen"}
    assert all(event.inference == "reviewed" and event.confidence == 1.0 for event in events)
    assert all(event.end_time is None for event in events)

    assert memory.title == "Putting keys down"
    assert db.scalars(select(MemoryObservation.observation_id).where(MemoryObservation.memory_id == memory.id)).all() == [
        observation.id
    ]
    linked_events = set(db.scalars(select(MemoryEvent.event_id).where(MemoryEvent.memory_id == memory.id)))
    assert linked_events == {event.id for event in events}
    assert saved.object_observation is not None
    assert saved.object_observation.object_name == "keys"
    assert saved.object_observation.memory_id == memory.id


def test_one_observation_can_contribute_to_several_events_and_an_event_to_several_observations(db: Session) -> None:
    user = make_user(db)
    first = create_observation(db, user.id, ObservationInput(timestamp=at(9, 0), location_label="Bedroom"))
    second = create_observation(
        db,
        user.id,
        ObservationInput(
            timestamp=at(9, 5),
            location_label="Kitchen",
            objects=[{"name": "kettle", "location": "counter", "confidence": 0.9}],
        ),
    )
    db.commit()

    events = observation_events(db, second.id)
    assert {event.event_type for event in events} == {"entered_location", "object_seen"}
    entered = next(event for event in events if event.event_type == "entered_location")
    assert entered.confidence < 1.0
    assert entered.inference == "rule:location_change"
    linked = set(db.scalars(select(EventObservation.observation_id).where(EventObservation.event_id == entered.id)))
    assert linked == {first.id, second.id}


def test_low_confidence_objects_and_unknown_people_do_not_create_events(db: Session) -> None:
    user = make_user(db)
    db.add(Person(user_id=user.id, name="Sarah", relationship="Daughter"))
    db.flush()
    observation = create_observation(
        db,
        user.id,
        ObservationInput(
            timestamp=at(9),
            people=["Sarah Zorblax", "sarah"],
            objects=[{"name": "remote", "confidence": 0.3}, {"name": "cup", "confidence": None}],
        ),
    )
    db.commit()

    assert observation.detected_people == [
        {"name": "Sarah Zorblax", "person_id": None},
        {"name": "Sarah", "person_id": 1},
    ]
    events = observation_events(db, observation.id)
    assert [(event.event_type, event.title) for event in events] == [("person_seen", "Saw Sarah")]


def test_activity_needs_several_agreeing_cues(db: Session) -> None:
    user = make_user(db)
    weak = create_observation(
        db, user.id, ObservationInput(timestamp=at(8, 0), location_label="Kitchen", description="An open fridge.")
    )
    assert observation_events(db, weak.id) == []

    strong = create_observation(
        db, user.id, ObservationInput(timestamp=at(8, 4), location_label="Kitchen", description="Eggs in a pan.")
    )
    db.commit()
    events = observation_events(db, strong.id)
    breakfast = [event for event in events if event.inference == "rule:preparing_breakfast"]
    assert len(breakfast) == 1
    assert breakfast[0].confidence < 1.0
    linked = set(db.scalars(select(EventObservation.observation_id).where(EventObservation.event_id == breakfast[0].id)))
    assert linked == {weak.id, strong.id}

    again = create_observation(
        db, user.id, ObservationInput(timestamp=at(8, 9), location_label="Kitchen", description="Toast and eggs.")
    )
    db.commit()
    assert [event.inference for event in observation_events(db, again.id)] == ["rule:preparing_breakfast"]
    assert db.scalar(select(Event).where(Event.inference == "rule:preparing_breakfast")).id == breakfast[0].id


def test_event_generation_can_run_later_for_stored_observations(db: Session) -> None:
    user = make_user(db)
    observation = create_observation(
        db,
        user.id,
        ObservationInput(timestamp=at(9), objects=[{"name": "wallet", "confidence": 0.95}]),
        generate_events=False,
    )
    assert observation_events(db, observation.id) == []
    generate_events(db, [observation])
    generate_events(db, [observation])
    db.commit()
    assert [event.event_type for event in observation_events(db, observation.id)] == ["object_seen"]


# --- Episodes --------------------------------------------------------------------


def test_episodes_group_nearby_events_and_split_on_gaps(db: Session) -> None:
    user = make_user(db)
    morning = [
        save_reviewed_moment(db, user.id, timestamp=at(9, minute), location="Kitchen", description=desc)
        for minute, desc in ((0, "Making tea."), (10, "Drinking tea."))
    ]
    later = save_reviewed_moment(db, user.id, timestamp=at(13), location="Garden", description="Watering plants.")
    episodes = consolidate_episodes(db, user.id)
    db.commit()

    assert len(episodes) == 2
    first, second = sorted(episodes, key=lambda episode: episode.start_time)
    assert first.start_time == at(9, 0)
    assert first.end_time == at(9, 10)
    assert first.location == "Kitchen"
    assert len(db.scalars(select(EpisodeEvent.event_id).where(EpisodeEvent.episode_id == first.id)).all()) == 2
    assert {saved.memory.episode_id for saved in morning} == {first.id}
    assert later.memory.episode_id == second.id

    assert consolidate_episodes(db, user.id) == []
    assert len(db.scalars(select(Episode)).all()) == 2


def test_a_new_event_joins_the_open_episode(db: Session) -> None:
    user = make_user(db)
    save_reviewed_moment(db, user.id, timestamp=at(9, 0), location="Kitchen", description="Making tea.")
    (episode,) = consolidate_episodes(db, user.id)
    saved = save_reviewed_moment(db, user.id, timestamp=at(9, 15), location="Kitchen", description="Washing up.")
    (updated,) = consolidate_episodes(db, user.id)
    db.commit()
    assert updated.id == episode.id
    assert updated.end_time == at(9, 15)
    assert saved.memory.episode_id == episode.id


# --- Canonical text --------------------------------------------------------------


def test_canonical_text_helpers_describe_each_level(db: Session) -> None:
    user = make_user(db)
    saved = save_reviewed_moment(
        db, user.id, timestamp=at(10), location="Kitchen", description="Keys on the counter.", object_name="keys"
    )
    (episode,) = consolidate_episodes(db, user.id)
    event = observation_events(db, saved.observation.id)[0]

    assert "Kitchen" in observation_to_text(saved.observation)
    assert "Keys on the counter." in observation_to_text(saved.observation)
    assert "keys" in event_to_text(event).casefold()
    assert "Kitchen" in episode_to_text(episode)
    assert "Keys on the counter." in memory_to_text(saved.memory)


# --- HTTP API --------------------------------------------------------------------


def test_seed_builds_the_full_hierarchy(client: TestClient) -> None:
    seed(client)
    memories = client.get("/api/memories").json()
    observations = client.get("/api/observations").json()
    events = client.get("/api/events").json()
    episodes = client.get("/api/episodes").json()

    assert len(observations) == len(memories) == 4
    assert all(observation["reviewed"] for observation in observations)
    assert len(events) >= len(memories)
    assert episodes
    assert all(memory["episode_id"] is not None and memory["episode_title"] for memory in memories)
    assert {event_id for episode in episodes for event_id in episode["event_ids"]} == {event["id"] for event in events}


def test_post_memories_keeps_its_response_and_builds_the_hierarchy(client: TestClient) -> None:
    seed(client)
    created = client.post(
        "/api/memories",
        files={"image": ("photo.jpg", b"fake-image-content", "image/jpeg")},
        data={
            "timestamp": at(10, 30).isoformat(),
            "location": "Hallway",
            "description": "Wallet on the hallway shelf.",
            "object_name": "wallet",
            "source": "browser_camera",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert set(body) == {"id", "timestamp", "location", "activity", "description", "image_url", "object_observation_id"}
    assert body["object_observation_id"] is not None

    observation = client.get("/api/observations").json()[0]
    assert observation["source"] == "browser_camera"
    assert observation["image_url"] == body["image_url"]
    events = {event["id"]: event for event in client.get("/api/events").json()}
    kinds = {events[event_id]["event_type"]: events[event_id] for event_id in observation["event_ids"]}
    assert kinds["recorded_activity"]["inference"] == "reviewed"
    assert kinds["object_seen"]["inference"] == "reviewed"

    listed = next(memory for memory in client.get("/api/memories").json() if memory["id"] == body["id"])
    assert listed["episode_id"] is not None
    rewind = client.get("/api/rewind", params={"include_earlier": "true"}).json()
    moment = next(item for item in rewind["moments"] if item["memory_id"] == body["id"])
    assert moment["episode_title"] == listed["episode_title"]
    assert client.get(body["image_url"]).status_code == 200


def test_post_memories_defaults_source_and_rejects_unknown_sources(client: TestClient) -> None:
    seed(client)
    data = {"timestamp": at(10, 30).isoformat(), "location": "Hallway", "description": "Coat on the hook."}
    files = {"image": ("photo.jpg", b"fake-image-content", "image/jpeg")}
    assert client.post("/api/memories", files=files, data={**data, "source": "pager"}).status_code == 422
    assert client.post("/api/memories", files=files, data=data).status_code == 201
    assert client.get("/api/observations").json()[0]["source"] == "other"


def test_post_observation_without_image(client: TestClient) -> None:
    seed(client)
    response = client.post(
        "/api/observations",
        data={"timestamp": at(11).isoformat(), "source": "meta_glasses", "transcript": "Sarah said hello."},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["image_url"] is None
    assert body["location_label"] is None
    assert body["people"] == []
    assert body["objects"] == []
    assert body["event_ids"] == []
    assert body["analysis"] is None
    assert "Sarah said hello." in body["text"]


def test_post_observation_runs_existing_vision_analysis(client: TestClient) -> None:
    seed(client)
    response = client.post(
        "/api/observations",
        files={"image": ("keys-on-table.jpg", b"fake-image-content", "image/jpeg")},
        data={"timestamp": at(11).isoformat(), "source": "iphone_camera", "people": "Sarah, Stranger"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["analysis"] == "demo_scene"
    assert body["location_label"] == "Table"
    assert body["objects"][0]["name"] == "keys"
    assert body["people"] == [
        {"name": "Sarah", "person_id": 1, "location": None, "confidence": None},
        {"name": "Stranger", "person_id": None, "location": None, "confidence": None},
    ]
    assert body["reviewed"] is False
    events = {event["id"]: event for event in client.get("/api/events").json()}
    kinds = {events[event_id]["event_type"] for event_id in body["event_ids"]}
    assert {"object_seen", "person_seen"} <= kinds
    assert all(events[event_id]["confidence"] < 1.0 for event_id in body["event_ids"])
    assert client.get(body["image_url"]).status_code == 200


def test_post_observation_without_vision_provider_still_stores_it(client: TestClient) -> None:
    seed(client)
    response = client.post(
        "/api/observations",
        files={"image": ("random.jpg", b"fake-image-content", "image/jpeg")},
        data={"timestamp": at(11).isoformat(), "source": "uploaded_image"},
    )
    assert response.status_code == 201
    assert response.json()["analysis"] == "not_configured"
    assert response.json()["description"] is None


@pytest.mark.parametrize(
    "data",
    [
        {"source": "browser_camera"},
        {"timestamp": "not-a-time", "source": "browser_camera"},
        {"timestamp": (datetime.now() + timedelta(days=5)).isoformat(), "source": "browser_camera"},
        {"timestamp": at(11).isoformat(), "source": "carrier_pigeon"},
        {"timestamp": at(11).isoformat(), "source": "other", "latitude": "24.4"},
    ],
)
def test_post_observation_rejects_invalid_input(client: TestClient, data: dict) -> None:
    seed(client)
    assert client.post("/api/observations", data=data).status_code == 422
    assert len(client.get("/api/observations").json()) == 4


def test_timeline_endpoints_are_isolated_per_user(client: TestClient) -> None:
    seed(client)
    created = client.post(
        "/api/observations",
        files={"image": ("keys-on-table.jpg", b"fake-image-content", "image/jpeg")},
        data={"timestamp": at(11).isoformat(), "source": "other"},
    ).json()
    other = {USER_ID_HEADER: "2"}

    alex_ids = {item["id"] for item in client.get("/api/observations").json()}
    jordan_ids = {item["id"] for item in client.get("/api/observations", headers=other).json()}
    assert created["id"] in alex_ids
    assert alex_ids.isdisjoint(jordan_ids)
    assert {e["id"] for e in client.get("/api/events").json()}.isdisjoint(
        {e["id"] for e in client.get("/api/events", headers=other).json()}
    )
    assert {e["id"] for e in client.get("/api/episodes").json()}.isdisjoint(
        {e["id"] for e in client.get("/api/episodes", headers=other).json()}
    )
    assert client.get(created["image_url"], headers=other).status_code == 404


def test_consolidate_endpoint_is_idempotent(client: TestClient) -> None:
    seed(client)
    client.post("/api/observations", data={"timestamp": at(12).isoformat(), "source": "other", "location_label": "Garden"})
    client.post("/api/observations", data={"timestamp": at(12, 5).isoformat(), "source": "other", "location_label": "Kitchen"})
    client.post("/api/episodes/consolidate")
    assert client.post("/api/episodes/consolidate").json() == {"episode_ids": []}


def test_events_can_be_filtered_by_confidence(client: TestClient) -> None:
    seed(client)
    client.post("/api/observations", data={"timestamp": at(12).isoformat(), "source": "other", "location_label": "Garden"})
    client.post("/api/observations", data={"timestamp": at(12, 5).isoformat(), "source": "other", "location_label": "Patio"})
    everything = client.get("/api/events").json()
    confident = client.get("/api/events", params={"min_confidence": 1.0}).json()
    assert any(event["inference"] == "rule:location_change" for event in everything)
    assert all(event["confidence"] == 1.0 for event in confident)
    assert len(confident) < len(everything)


# --- Queries over the new layer ------------------------------------------------


def test_existing_questions_still_answer_from_saved_moments(client: TestClient) -> None:
    seed(client)
    keys = client.post("/api/query", json={"question": "Where are my keys?"}).json()
    assert keys["intent"] == "object_location"
    assert "kitchen counter" in keys["answer"]
    doing = client.post("/api/query", json={"question": "What was I doing?"}).json()
    assert doing["intent"] == "recent_activity"
    assert "preparing to leave" in doing["answer"]
    sarah = client.post("/api/query", json={"question": "Who is Sarah?"}).json()
    assert sarah["intent"] == "person_lookup"
    assert "daughter" in sarah["answer"]
    passport = client.post("/api/query", json={"question": "Where is my passport?"}).json()
    assert passport["intent"] == "unknown"
    assert passport["source_ids"] == []


def test_what_did_i_do_today_lists_saved_moments_with_episodes(client: TestClient) -> None:
    seed(client)
    answer = client.post("/api/query", json={"question": "What did I do today?"}).json()
    assert answer["intent"] == "day_summary"
    assert answer["answer"].startswith("Today you saved 4 moments")
    assert "making tea" in answer["answer"]
    assert any(source.startswith("episode:") for source in answer["source_ids"])
    assert sum(source.startswith("memory:") for source in answer["source_ids"]) == 4

    arabic = client.post("/api/query", json={"question": "ماذا فعلت اليوم؟", "language": "ar"}).json()
    assert arabic["intent"] == "day_summary"

    schedule = client.post("/api/query", json={"question": "What am I doing today?"}).json()
    assert schedule["intent"] == "schedule"


def test_day_summary_says_it_does_not_know_without_saved_moments(db: Session) -> None:
    user = make_user(db)
    create_observation(db, user.id, ObservationInput(timestamp=datetime.now(), transcript="Unreviewed chatter."))
    db.commit()
    answer = answer_question(db, user.id, "What did I do today?")
    assert answer.intent == "unknown"
    assert answer.source_ids == []


def test_unreviewed_observations_never_become_spoken_answers(client: TestClient) -> None:
    seed(client)
    client.post(
        "/api/observations",
        files={"image": ("keys-on-table.jpg", b"fake-image-content", "image/jpeg")},
        data={"timestamp": at(11, 50).isoformat(), "source": "meta_glasses"},
    )
    keys = client.post("/api/query", json={"question": "Where are my keys?"}).json()
    assert "kitchen counter" in keys["answer"]
    assert "dark table" not in keys["answer"]


def test_caregiver_correction_flows_into_events_and_keeps_the_observation(client: TestClient, db: Session) -> None:
    seed(client)
    memory_id = next(m["id"] for m in client.get("/api/memories").json() if "keys" in m["description"])
    corrected = client.post(
        f"/api/caregiver/patients/1/moments/{memory_id}/corrections",
        json={"field": "object_location", "value": "blue drawer"},
        headers={"X-MemoryCue-Caregiver-Id": "1"},
    )
    assert corrected.status_code == 201

    events = list(
        db.scalars(select(Event).join(MemoryEvent, MemoryEvent.event_id == Event.id).where(MemoryEvent.memory_id == memory_id))
    )
    object_event = next(event for event in events if event.event_type == "object_seen")
    assert object_event.title == "keys seen on the blue drawer"
    observation_id = db.scalar(select(MemoryObservation.observation_id).where(MemoryObservation.memory_id == memory_id))
    observation = db.get(Observation, observation_id)
    assert observation.detected_objects[0]["location"] == "kitchen counter"
    assert latest_correction(db, memory_id) is not None
    assert "blue drawer" in client.post("/api/query", json={"question": "Where are my keys?"}).json()["answer"]


# --- Migration -------------------------------------------------------------------

LEGACY_MEMORY_TABLES = {"memories", "memory_observations", "memory_events", "memory_corrections", "object_observations"}


def build_legacy_database(engine) -> None:
    """The schema before this change: a memories table with only its original columns."""

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(
        bind=engine,
        tables=[table for table in Base.metadata.sorted_tables if table.name not in LEGACY_MEMORY_TABLES],
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE memories (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), "
                "timestamp DATETIME NOT NULL, location VARCHAR(120) NOT NULL, activity VARCHAR(200), "
                "description TEXT NOT NULL, image_path VARCHAR(255))"
            )
        )
        connection.execute(text("INSERT INTO users (id, name) VALUES (1, 'Alex'), (2, 'Jordan')"))
        connection.execute(text("INSERT INTO people (user_id, name, relationship) VALUES (1, 'Sarah', 'Daughter')"))
        connection.execute(
            text("INSERT INTO schedule_items (user_id, title, scheduled_at) VALUES (1, 'Dinner', :when)"),
            {"when": at(18)},
        )
        rows = [
            (7, 1, at(10, 0), "Kitchen", "making tea", "Alex was making tea.", "old-photo.jpg"),
            (9, 1, at(10, 18), "Kitchen", None, "Keys on the counter.", None),
            (12, 2, at(10, 5), "Bedroom", "packing", "Jordan was packing.", None),
        ]
        for row in rows:
            connection.execute(
                text("INSERT INTO memories VALUES (:id, :user_id, :ts, :loc, :act, :desc, :img)"),
                dict(zip(("id", "user_id", "ts", "loc", "act", "desc", "img"), row)),
            )
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO object_observations (user_id, object_name, location, observed_at, memory_id) "
                "VALUES (1, 'keys', 'kitchen counter', :when, 9)"
            ),
            {"when": at(10, 18)},
        )


def test_migration_backfills_legacy_memories_without_inventing_facts(engine, session_factory) -> None:
    build_legacy_database(engine)
    run_migrations(engine, session_factory)

    with session_factory() as db:
        memories = {memory.id: memory for memory in db.scalars(select(Memory))}
        assert set(memories) == {7, 9, 12}
        assert memories[7].image_path == "old-photo.jpg"
        assert memories[7].description == "Alex was making tea."
        assert db.scalar(select(Person.name)) == "Sarah"
        assert db.scalar(select(ScheduleItem.title)) == "Dinner"
        assert db.scalar(select(ObjectObservation.memory_id)) == 9

        for memory in memories.values():
            observation_id = db.scalar(select(MemoryObservation.observation_id).where(MemoryObservation.memory_id == memory.id))
            observation = db.get(Observation, observation_id)
            assert observation.user_id == memory.user_id
            assert observation.timestamp == memory.timestamp
            assert observation.image_path == memory.image_path
            assert observation.source == "other"
            assert observation.extra == {"migrated_from_memory_id": memory.id, "original_source": "unknown"}
            assert observation.latitude is None and observation.longitude is None
            assert observation.detected_people == []

            event_ids = db.scalars(select(MemoryEvent.event_id).where(MemoryEvent.memory_id == memory.id)).all()
            events = [db.get(Event, event_id) for event_id in event_ids]
            assert events and all(event.inference == "legacy_migration" for event in events)
            assert all(event.end_time is None for event in events)
            assert memory.end_time is None
            assert memory.episode_id is not None

        keys_observation_id = db.scalar(select(MemoryObservation.observation_id).where(MemoryObservation.memory_id == 9))
        assert db.get(Observation, keys_observation_id).detected_objects[0]["name"] == "keys"
        episodes = db.scalars(select(Episode)).all()
        assert {episode.user_id for episode in episodes} == {1, 2}

        assert "kitchen counter" in answer_question(db, 1, "Where are my keys?").answer
        assert "making tea" in answer_question(db, 1, "What was I doing at 10 AM?").answer
        assert answer_question(db, 2, "Where are my keys?").intent == "unknown"

        counts = (
            len(db.scalars(select(Observation)).all()),
            len(db.scalars(select(Event)).all()),
            len(db.scalars(select(Episode)).all()),
        )

    run_migrations(engine, session_factory)
    with session_factory() as db:
        assert backfill_legacy_memories(db) == 0
        assert counts == (
            len(db.scalars(select(Observation)).all()),
            len(db.scalars(select(Event)).all()),
            len(db.scalars(select(Episode)).all()),
        )


def test_app_still_serves_legacy_data_after_migration(engine, session_factory, client: TestClient) -> None:
    build_legacy_database(engine)
    run_migrations(engine, session_factory)

    memories = client.get("/api/memories").json()
    assert [memory["id"] for memory in memories] == [9, 7]
    assert memories[1]["image_url"] == "/api/media/old-photo.jpg"
    rewind = client.get("/api/rewind", params={"include_earlier": "true"}).json()
    assert {moment["memory_id"] for moment in rewind["moments"]} == {7, 9}
    assert client.get("/api/observations").json()[0]["metadata"]["original_source"] == "unknown"


# --- Review regressions -------------------------------------------------------


def test_unreviewed_captures_never_reach_spoken_or_wearer_facing_episode_labels(client: TestClient) -> None:
    seed(client)
    captured = client.post(
        "/api/observations",
        data={"timestamp": at(10, 12).isoformat(), "source": "meta_glasses", "location_label": "Garden shed", "people": "Sarah"},
    )
    assert captured.status_code == 201
    assert client.post("/api/episodes/consolidate").status_code == 200

    summary = client.post("/api/query", json={"question": "What did I do today?"}).json()
    episode_labels = [item["label"] for item in summary["evidence"] if item["source_id"].startswith("episode:")]
    assert episode_labels
    spoken_surface = " ".join([summary["answer"], *(item["label"] + item["detail"] for item in summary["evidence"])])
    assert "Garden shed" not in spoken_surface
    assert "Sarah" not in spoken_surface
    assert "Getting ready to leave" not in spoken_surface

    rewind = client.get("/api/rewind", params={"include_earlier": "true"}).json()["moments"]
    memories = client.get("/api/memories").json()
    titles = {item["episode_title"] for item in [*rewind, *memories] if item.get("episode_title")}
    assert titles and all("Garden shed" not in title and "Getting ready" not in title for title in titles)
    assert "kitchen counter" in client.post("/api/query", json={"question": "Where are my keys?"}).json()["answer"]


def test_failed_event_inference_still_saves_the_observation(client: TestClient, db: Session, monkeypatch) -> None:
    def broken(*_args, **_kwargs):
        raise RuntimeError("event rule crashed")

    monkeypatch.setattr("app.observation_service.events_for_observation", broken)
    user = make_user(db)
    observation = create_observation(db, user.id, ObservationInput(timestamp=at(9), description="Something happened."))
    db.commit()
    assert db.get(Observation, observation.id) is not None
    assert observation_events(db, observation.id) == []

    seed(client)
    created = client.post("/api/observations", data={"timestamp": at(9, 30).isoformat(), "source": "iphone_camera"})
    assert created.status_code == 201
    saved = client.post(
        "/api/memories",
        files={"image": ("photo.jpg", b"fake-image-content", "image/jpeg")},
        data={"timestamp": at(9, 40).isoformat(), "location": "Hall", "description": "Coat on the hook."},
    )
    assert saved.status_code == 201
    assert saved.json()["id"] in {memory["id"] for memory in client.get("/api/memories").json()}


def test_failed_background_consolidation_keeps_saved_data(client: TestClient, monkeypatch) -> None:
    seed(client)

    def broken(*_args, **_kwargs):
        raise RuntimeError("grouping crashed")

    monkeypatch.setattr("app.episode_service.consolidate_episodes", broken)
    created = client.post("/api/observations", data={"timestamp": at(9, 30).isoformat(), "source": "browser_camera"})
    assert created.status_code == 201
    assert created.json()["id"] in {item["id"] for item in client.get("/api/observations").json()}


def test_episode_gap_boundary_is_inclusive_and_ties_are_deterministic(db: Session) -> None:
    user = make_user(db)
    for when in (at(9, 0), at(9, 20), at(9, 40) + timedelta(seconds=1)):
        save_reviewed_moment(db, user.id, timestamp=when, location="Kitchen", description=f"Moment at {when:%H:%M:%S}.")
    db.flush()
    consolidate_episodes(db, user.id)
    before = {
        "observations": len(db.scalars(select(Observation)).all()),
        "events": len(db.scalars(select(Event)).all()),
        "memories": len(db.scalars(select(Memory)).all()),
    }
    episodes = db.scalars(select(Episode).order_by(Episode.start_time)).all()
    assert [(episode.start_time, episode.end_time) for episode in episodes] == [
        (at(9, 0), at(9, 20)),
        (at(9, 40) + timedelta(seconds=1), None),
    ]

    # Exactly between two episodes: joins the earlier one, every time.
    save_reviewed_moment(db, user.id, timestamp=at(9, 30) + timedelta(milliseconds=500), location="Kitchen", description="Between.")
    db.flush()
    consolidate_episodes(db, user.id)
    consolidate_episodes(db, user.id)
    middle = db.scalar(select(Memory).where(Memory.description == "Between."))
    assert middle.episode_id == episodes[0].id
    assert len(db.scalars(select(EpisodeEvent)).all()) == len(db.scalars(select(Event)).all())
    assert len(db.scalars(select(Observation)).all()) == before["observations"] + 1
    assert len(db.scalars(select(Memory)).all()) == before["memories"] + 1


CAPTURED_AT = datetime.combine(date.today(), time(10, 15, 27))


def capture(client: TestClient, source: str = "browser_camera", **data) -> dict:
    response = client.post(
        "/api/observations",
        files={"image": ("glasses-capture.jpg", b"captured-frame", "image/jpeg")},
        data={"timestamp": CAPTURED_AT.isoformat(), "source": source, "analyze": "false", **data},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.parametrize("source", ["browser_camera", "iphone_camera", "meta_glasses"])
def test_a_capture_becomes_a_normalized_unreviewed_observation(client: TestClient, db: Session, source: str) -> None:
    seed(client)
    memories_before = client.get("/api/memories").json()
    objects_before = db.scalar(select(func.count()).select_from(ObjectObservation))

    body = capture(client, source)

    assert body["source"] == source
    assert body["timestamp"] == CAPTURED_AT.isoformat()
    assert body["reviewed"] is False
    assert body["latitude"] is None and body["longitude"] is None and body["location_label"] is None
    assert body["description"] is None and body["activity"] is None and body["analysis"] is None
    assert client.get(body["image_url"]).content == b"captured-frame"
    assert db.get(Observation, body["id"]).image_path == body["image_url"].removeprefix("/api/media/")
    assert client.get("/api/memories").json() == memories_before
    assert db.scalar(select(func.count()).select_from(ObjectObservation)) == objects_before


def test_a_capture_keeps_a_supplied_location(client: TestClient) -> None:
    seed(client)
    body = capture(client, latitude="24.4539", longitude="54.3773")
    assert (body["latitude"], body["longitude"]) == (24.4539, 54.3773)
    assert body["location_label"] is None


def test_a_capture_survives_failed_event_inference(client: TestClient, monkeypatch) -> None:
    def broken(*_args, **_kwargs):
        raise RuntimeError("event rule crashed")

    monkeypatch.setattr("app.observation_service.events_for_observation", broken)
    seed(client)
    body = capture(client)
    assert body["event_ids"] == []
    stored = {item["id"]: item for item in client.get("/api/observations").json()}[body["id"]]
    assert stored["source"] == "browser_camera"
    assert client.get(stored["image_url"]).status_code == 200


def test_an_analyzed_camera_capture_is_never_a_grounded_answer(client: TestClient) -> None:
    seed(client)
    memories_before = client.get("/api/memories").json()
    response = client.post(
        "/api/observations",
        files={"image": ("keys-on-table.jpg", b"captured-frame", "image/jpeg")},
        data={"timestamp": at(11, 50).isoformat(), "source": "browser_camera"},
    )
    assert response.status_code == 201
    observation = response.json()
    assert observation["objects"][0]["name"] == "keys"
    assert observation["event_ids"]
    assert client.post("/api/episodes/consolidate").status_code == 200

    keys = client.post("/api/query", json={"question": "Where are my keys?"}).json()
    assert "kitchen counter" in keys["answer"]
    assert "dark table" not in keys["answer"]
    summary = client.post("/api/query", json={"question": "What did I do today?"}).json()
    spoken = " ".join([summary["answer"], *(item["label"] + item["detail"] for item in summary["evidence"])])
    assert "Preparing to leave" not in spoken and "dark table" not in spoken
    assert all(not source_id.startswith(("observation:", "event:")) for source_id in keys["source_ids"] + summary["source_ids"])
    assert client.get("/api/memories").json() == memories_before


def test_saving_a_reviewed_capture_links_it_without_editing_it(client: TestClient, db: Session) -> None:
    seed(client)
    raw = capture(client)
    saved = client.post(
        "/api/memories",
        data={
            "observation_id": str(raw["id"]),
            "timestamp": CAPTURED_AT.isoformat(),
            "location": "Hallway table",
            "description": "My wallet is on the hallway table.",
            "object_name": "Wallet",
        },
    )
    assert saved.status_code == 201
    body = saved.json()
    assert body["image_url"] == raw["image_url"]
    assert body["timestamp"] == CAPTURED_AT.isoformat()
    assert body["object_observation_id"] is not None

    unchanged = db.get(Observation, raw["id"])
    assert unchanged.reviewed is False
    assert unchanged.location_label is None and unchanged.description is None
    assert unchanged.detected_objects == []
    linked = set(db.scalars(select(MemoryObservation.observation_id).where(MemoryObservation.memory_id == body["id"])))
    assert raw["id"] in linked
    reviewed = db.get(Observation, next(iter(linked - {raw["id"]})))
    assert reviewed.reviewed is True
    assert reviewed.source == "browser_camera"
    assert reviewed.extra["reviewed_from_observation_id"] == raw["id"]

    wallet = client.post("/api/query", json={"question": "Where is my wallet?"}).json()
    assert "Hallway table" in wallet["answer"]
    assert body["id"] in {memory["id"] for memory in client.get("/api/memories").json()}
    assert client.get(body["image_url"]).status_code == 200
    assert client.get(body["image_url"], headers={USER_ID_HEADER: "2"}).status_code == 404

    again = {"timestamp": CAPTURED_AT.isoformat(), "location": "Hall", "description": "Again."}
    assert client.post("/api/memories", data={**again, "observation_id": str(reviewed.id)}).status_code == 422
    assert client.post("/api/memories", data={**again, "observation_id": str(raw["id"])}).status_code == 409


def test_saving_a_capture_is_scoped_to_its_owner_and_needs_one_image(client: TestClient) -> None:
    seed(client)
    raw = capture(client)
    form = {"timestamp": CAPTURED_AT.isoformat(), "location": "Hall", "description": "Coat on the hook."}

    other_user = client.post("/api/memories", data={**form, "observation_id": str(raw["id"])}, headers={USER_ID_HEADER: "2"})
    assert other_user.status_code == 404
    both = client.post(
        "/api/memories",
        files={"image": ("photo.jpg", b"fake-image-content", "image/jpeg")},
        data={**form, "observation_id": str(raw["id"])},
    )
    assert both.status_code == 422
    assert client.post("/api/memories", data=form).status_code == 422
    imageless = client.post("/api/observations", data={"timestamp": CAPTURED_AT.isoformat(), "source": "browser_camera"}).json()
    assert client.post("/api/memories", data={**form, "observation_id": str(imageless["id"])}).status_code == 422


def test_captures_use_database_media_storage(client: TestClient, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MEDIA_STORAGE", "database")
    seed(client)
    raw = capture(client)
    media_directory = tmp_path / "media"
    assert not media_directory.exists() or not list(media_directory.iterdir())
    listed = {item["id"]: item for item in client.get("/api/observations").json()}[raw["id"]]
    assert client.get(listed["image_url"]).content == b"captured-frame"
    assert client.get(listed["image_url"], headers={USER_ID_HEADER: "2"}).status_code == 404

    saved = client.post(
        "/api/memories",
        data={"observation_id": str(raw["id"]), "timestamp": CAPTURED_AT.isoformat(), "location": "Hall", "description": "Coat."},
    )
    assert saved.status_code == 201
    assert client.get(saved.json()["image_url"]).content == b"captured-frame"


# --- Rewind photo provenance --------------------------------------------------


def rewind_sources(client: TestClient) -> dict[str, str]:
    moments = client.get("/api/rewind", params={"window_minutes": 1440, "include_earlier": "true"}).json()["moments"]
    return {moment["description"]: moment["source"] for moment in moments}


def upload_reviewed(client: TestClient, description: str, minute: int, filename: str = "photo.jpg", **data) -> dict:
    response = client.post(
        "/api/memories",
        files={"image": (filename, b"uploaded-photo", "image/jpeg")},
        data={"timestamp": at(23, minute).isoformat(), "location": "Hall", "description": description, **data},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.parametrize("source", ["browser_camera", "iphone_camera", "meta_glasses"])
def test_rewind_labels_a_saved_device_capture_as_live(client: TestClient, db: Session, source: str) -> None:
    seed(client)
    raw = capture(client, source)
    saved = client.post(
        "/api/memories",
        data={"observation_id": str(raw["id"]), "timestamp": at(23, 55).isoformat(), "location": "Hall", "description": "Coat on hook."},
    )
    assert saved.status_code == 201

    reviewed = db.scalars(
        select(Observation).join(MemoryObservation).where(
            MemoryObservation.memory_id == saved.json()["id"], Observation.reviewed.is_(True)
        )
    ).one()
    assert reviewed.source == source
    assert reviewed.extra["reviewed_from_observation_id"] == raw["id"]
    assert rewind_sources(client)["Coat on hook."] == "capture"


def test_rewind_does_not_call_uploaded_or_demo_scene_photos_live(client: TestClient) -> None:
    seed(client)
    upload_reviewed(client, "Uploaded photo.", 50, source="uploaded_image")
    upload_reviewed(client, "Demo scene.", 51, filename="keys-on-table.jpg", source="uploaded_image")
    upload_reviewed(client, "Unknown origin.", 52)

    sources = rewind_sources(client)
    assert sources["Uploaded photo."] == "upload"
    assert sources["Demo scene."] == "upload"
    assert sources["Unknown origin."] == "photo"


def test_rewind_keeps_seeded_photo_less_moments_as_samples(client: TestClient) -> None:
    seed(client)
    moments = client.get("/api/rewind", params={"window_minutes": 1440, "include_earlier": "true"}).json()["moments"]
    assert moments
    assert all(moment["image_url"] is None and moment["source"] == "sample" for moment in moments)


def test_rewind_labels_a_legacy_photo_of_unknown_origin_as_a_saved_photo(db: Session) -> None:
    user = make_user(db)
    memory = Memory(user_id=user.id, timestamp=at(9), location="Hall", activity="", description="Legacy.", image_path="legacy.jpg")
    db.add(memory)
    db.commit()
    backfill_legacy_memories(db)
    db.commit()

    moments = build_rewind(db, user.id, window_minutes=1440, include_earlier=True, now=at(10)).moments
    assert [moment.source for moment in moments] == ["photo"]


def test_every_observation_source_has_a_rewind_label() -> None:
    assert set(PHOTO_ORIGINS) == set(OBSERVATION_SOURCES)
    assert {source for source, origin in PHOTO_ORIGINS.items() if origin == "capture"} == {
        "browser_camera",
        "iphone_camera",
        "meta_glasses",
    }
