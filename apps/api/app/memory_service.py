"""Saving a reviewed moment as Observation -> Events -> Memory."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .episode_service import refresh_episode
from .event_service import REVIEWED_INFERENCES
from .models import (
    Episode,
    Event,
    EventObservation,
    Memory,
    MemoryEvent,
    MemoryObservation,
    ObjectObservation,
    Observation,
)
from .observation_service import ObservationInput, create_observation


@dataclass
class SavedMoment:
    memory: Memory
    observation: Observation
    events: list[Event]
    object_observation: ObjectObservation | None


def save_reviewed_moment(
    db: Session,
    user_id: int,
    *,
    timestamp: datetime,
    location: str,
    description: str,
    activity: str = "",
    object_name: str = "",
    object_location: str | None = None,
    image_path: str | None = None,
    source: str = "other",
    metadata: dict | None = None,
) -> SavedMoment:
    """Store a wearer-reviewed moment through the observation pipeline.

    The Memory keeps its long-standing columns, so existing answers, rewind,
    corrections, and cues read it unchanged; the observation and events beneath
    it are the evidence chain. Episode grouping happens later.
    """

    normalized_object = object_name.strip().casefold()
    object_location = object_location or location
    observation = create_observation(
        db,
        user_id,
        ObservationInput(
            timestamp=timestamp,
            source=source,
            image_path=image_path,
            location_label=location,
            description=description,
            activity=activity or None,
            objects=[{"name": normalized_object, "location": object_location, "confidence": None}]
            if normalized_object
            else [],
            reviewed=True,
            metadata=metadata or {},
        ),
    )
    events = observation_events(db, observation.id)
    now = datetime.now()
    memory = Memory(
        user_id=user_id,
        timestamp=observation.timestamp,
        location=location,
        activity=activity,
        description=description,
        image_path=image_path,
        title=(activity or None),
        objects=list(observation.detected_objects),
        people=list(observation.detected_people),
        created_at=now,
        updated_at=now,
    )
    db.add(memory)
    db.flush()
    link_memory(db, memory, observation, events)

    object_observation = None
    if normalized_object:
        object_observation = ObjectObservation(
            user_id=user_id,
            object_name=normalized_object,
            location=object_location,
            observed_at=observation.timestamp,
            memory_id=memory.id,
        )
        db.add(object_observation)
        db.flush()
    return SavedMoment(memory, observation, events, object_observation)


def observation_events(db: Session, observation_id: int) -> list[Event]:
    return list(
        db.scalars(
            select(Event)
            .join(EventObservation, EventObservation.event_id == Event.id)
            .where(EventObservation.observation_id == observation_id)
            .order_by(Event.start_time, Event.id)
        )
    )


def link_memory(db: Session, memory: Memory, observation: Observation, events: list[Event]) -> None:
    db.add(MemoryObservation(memory_id=memory.id, observation_id=observation.id))
    for event in events:
        db.add(MemoryEvent(memory_id=memory.id, event_id=event.id))
    db.flush()


def sync_memory_events(db: Session, memory: Memory) -> None:
    """Carry a caregiver correction into the reviewed events and episode built from it.

    Observations stay untouched: they are the original evidence.
    """

    object_rows = list(
        db.scalars(select(ObjectObservation).where(ObjectObservation.memory_id == memory.id).order_by(ObjectObservation.id))
    )
    objects = [{"name": row.object_name, "location": row.location, "confidence": None} for row in object_rows]
    events = db.scalars(
        select(Event)
        .join(MemoryEvent, MemoryEvent.event_id == Event.id)
        .where(MemoryEvent.memory_id == memory.id, Event.inference.in_(REVIEWED_INFERENCES))
    )
    for event in events:
        if event.event_type == "recorded_activity":
            event.title = (memory.activity or memory.description)[:200]
            event.description = memory.description
            event.objects = objects
        elif event.event_type == "object_seen" and object_rows:
            row = object_rows[0]
            event.title = f"{row.object_name} seen on the {row.location}"
            event.location = row.location
            event.objects = objects[:1]
    memory.objects = objects
    if memory.activity:
        memory.title = memory.activity
    memory.updated_at = datetime.now()
    db.flush()
    episode = db.get(Episode, memory.episode_id) if memory.episode_id else None
    if episode is not None:
        refresh_episode(db, episode)
