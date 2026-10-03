"""Idempotent schema upgrades and backfill for the observation hierarchy.

There is no Alembic here: `create_all` adds the new tables, `add_missing_columns`
adds nullable columns to existing tables on SQLite and Postgres, and
`backfill_legacy_memories` gives every pre-existing Memory a minimal
Observation -> Event chain and then groups events into episodes. Nothing is
deleted or rewritten, and only data already stored is copied.
"""

from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.orm import Session

from .database import advisory_lock
from .episode_service import consolidate_episodes
from .memory_service import link_memory
from .models import (
    Event,
    EventObservation,
    Memory,
    MemoryObservation,
    ObjectObservation,
    Observation,
    User,
)

MIGRATION_LOCK_ID = 8412557302

# Column name -> DDL type, added to `memories` when missing. All are nullable.
MEMORY_COLUMNS = {
    "image_path": "VARCHAR(255)",
    "title": "VARCHAR(200)",
    "end_time": "TIMESTAMP",
    "people": "JSON",
    "objects": "JSON",
    "episode_id": "INTEGER REFERENCES episodes(id)",
    "importance": "FLOAT",
    "embedding_ref": "VARCHAR(255)",
    "created_at": "TIMESTAMP",
    "updated_at": "TIMESTAMP",
}


def add_missing_columns(engine: Engine) -> list[str]:
    existing = {column["name"] for column in inspect(engine).get_columns("memories")}
    added = [name for name in MEMORY_COLUMNS if name not in existing]
    if added:
        with engine.begin() as connection:
            for name in added:
                connection.execute(text(f"ALTER TABLE memories ADD COLUMN {name} {MEMORY_COLUMNS[name]}"))
    return added


def legacy_memories(db: Session) -> list[Memory]:
    linked = select(MemoryObservation.memory_id)
    return list(
        db.scalars(select(Memory).where(Memory.id.not_in(linked)).order_by(Memory.user_id, Memory.timestamp, Memory.id))
    )


def backfill_memory(db: Session, memory: Memory) -> None:
    """Copy one legacy memory into the hierarchy without inventing anything.

    The capture source was never recorded, so it is "other" with
    `metadata.original_source = "unknown"`; no end time, coordinates,
    people, or creation time are filled in.
    """

    objects = [
        {"name": row.object_name, "location": row.location, "confidence": None}
        for row in db.scalars(
            select(ObjectObservation).where(ObjectObservation.memory_id == memory.id).order_by(ObjectObservation.id)
        )
    ]
    observation = Observation(
        user_id=memory.user_id,
        timestamp=memory.timestamp,
        source="other",
        image_path=memory.image_path,
        location_label=memory.location,
        description=memory.description,
        activity=memory.activity or None,
        detected_people=[],
        detected_objects=objects,
        reviewed=True,
        extra={"migrated_from_memory_id": memory.id, "original_source": "unknown"},
        created_at=None,
    )
    db.add(observation)
    db.flush()
    event = Event(
        user_id=memory.user_id,
        start_time=memory.timestamp,
        end_time=None,
        event_type="recorded_activity",
        title=(memory.activity or memory.description)[:200],
        description=memory.description,
        confidence=1.0,
        inference="legacy_migration",
        location=memory.location,
        people=[],
        objects=objects,
        created_at=None,
    )
    db.add(event)
    db.flush()
    db.add(EventObservation(event_id=event.id, observation_id=observation.id))
    link_memory(db, memory, observation, [event])
    if memory.objects is None:
        memory.objects = objects
    if memory.people is None:
        memory.people = []
    if memory.title is None and memory.activity:
        memory.title = memory.activity


def backfill_legacy_memories(db: Session) -> int:
    memories = legacy_memories(db)
    for memory in memories:
        backfill_memory(db, memory)
    user_ids = {memory.user_id for memory in memories}
    for user_id in sorted(user_ids):
        consolidate_episodes(db, user_id)
    return len(memories)


def run_migrations(engine: Engine, session_factory) -> int:
    """Bring an existing database up to the current schema; safe to run repeatedly."""

    add_missing_columns(engine)
    with session_factory() as db:
        with advisory_lock(db, MIGRATION_LOCK_ID):
            if not db.scalar(select(User.id).limit(1)):
                return 0
            migrated = backfill_legacy_memories(db)
            db.commit()
            return migrated
