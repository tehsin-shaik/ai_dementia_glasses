"""Every read the answer layer needs, across observations, events, episodes, and memories.

Spoken answers only use reviewed records: memories, their linked events, and
caregiver-entered people, objects, and schedules. Unreviewed observations and
rule-inferred events are retrievable here for timelines and future features,
with their confidence, but `query_service` does not speak them as facts.
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from .models import (
    Episode,
    EpisodeEvent,
    EpisodeObservation,
    Event,
    EventObservation,
    ImportantObject,
    Memory,
    ObjectObservation,
    Observation,
    Person,
    ScheduleItem,
)

MAX_LIMIT = 200


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min)
    return start, start + timedelta(days=1)


def _limit(limit: int) -> int:
    return max(1, min(limit, MAX_LIMIT))


def latest_activity_memory(
    db: Session, user_id: int, at: datetime | None = None, lookback: timedelta | None = None
) -> Memory | None:
    """The latest saved moment with an activity, optionally the one in progress at `at`."""

    query = select(Memory).where(
        Memory.user_id == user_id, Memory.activity.is_not(None), Memory.activity != ""
    )
    if at is not None:
        query = query.where(Memory.timestamp <= at)
        if lookback is not None:
            query = query.where(Memory.timestamp >= at - lookback)
    return db.scalar(query.order_by(Memory.timestamp.desc(), Memory.id.desc()).limit(1))


def known_object_names(db: Session, user_id: int) -> set[str]:
    observed = db.scalars(
        select(ObjectObservation.object_name).where(ObjectObservation.user_id == user_id).distinct()
    )
    important = db.scalars(
        select(ImportantObject.name).where(ImportantObject.user_id == user_id).distinct()
    )
    return {name.casefold() for name in observed} | {name.casefold() for name in important}


def latest_object_observation(db: Session, user_id: int, object_name: str) -> ObjectObservation | None:
    return db.scalar(
        select(ObjectObservation)
        .where(ObjectObservation.user_id == user_id, ObjectObservation.object_name == object_name)
        .order_by(ObjectObservation.observed_at.desc(), ObjectObservation.id.desc())
        .limit(1)
    )


def find_person(db: Session, user_id: int, name: str) -> Person | None:
    return db.scalar(
        select(Person).where(Person.user_id == user_id, Person.name.ilike(name)).order_by(Person.id).limit(1)
    )


def schedule_for_day(db: Session, user_id: int, day: date) -> list[ScheduleItem]:
    start, end = day_bounds(day)
    return list(
        db.scalars(
            select(ScheduleItem)
            .where(
                ScheduleItem.user_id == user_id,
                ScheduleItem.scheduled_at >= start,
                ScheduleItem.scheduled_at < end,
            )
            .order_by(ScheduleItem.scheduled_at, ScheduleItem.id)
        )
    )


def memories_for_day(db: Session, user_id: int, day: date) -> list[Memory]:
    start, end = day_bounds(day)
    return list(
        db.scalars(
            select(Memory)
            .where(Memory.user_id == user_id, Memory.timestamp >= start, Memory.timestamp < end)
            .order_by(Memory.timestamp, Memory.id)
        )
    )


def _in_window(query: Select, column, day: date | None, since: datetime | None) -> Select:
    if day is not None:
        start, end = day_bounds(day)
        query = query.where(column >= start, column < end)
    if since is not None:
        query = query.where(column >= since)
    return query


def list_observations(
    db: Session, user_id: int, *, day: date | None = None, since: datetime | None = None, limit: int = 50
) -> list[Observation]:
    query = _in_window(select(Observation).where(Observation.user_id == user_id), Observation.timestamp, day, since)
    return list(db.scalars(query.order_by(Observation.timestamp.desc(), Observation.id.desc()).limit(_limit(limit))))


def list_events(
    db: Session,
    user_id: int,
    *,
    day: date | None = None,
    since: datetime | None = None,
    min_confidence: float = 0.0,
    limit: int = 50,
) -> list[Event]:
    query = _in_window(
        select(Event).where(Event.user_id == user_id, Event.confidence >= min_confidence),
        Event.start_time,
        day,
        since,
    )
    return list(db.scalars(query.order_by(Event.start_time.desc(), Event.id.desc()).limit(_limit(limit))))


def list_episodes(
    db: Session, user_id: int, *, day: date | None = None, since: datetime | None = None, limit: int = 20
) -> list[Episode]:
    query = _in_window(select(Episode).where(Episode.user_id == user_id), Episode.start_time, day, since)
    return list(db.scalars(query.order_by(Episode.start_time.desc(), Episode.id.desc()).limit(_limit(limit))))


def observation_ids_for_events(db: Session, event_ids: list[int]) -> dict[int, list[int]]:
    linked: dict[int, list[int]] = {event_id: [] for event_id in event_ids}
    if not event_ids:
        return linked
    for event_id, observation_id in db.execute(
        select(EventObservation.event_id, EventObservation.observation_id)
        .where(EventObservation.event_id.in_(event_ids))
        .order_by(EventObservation.observation_id)
    ):
        linked[event_id].append(observation_id)
    return linked


def event_ids_for_observations(db: Session, observation_ids: list[int]) -> dict[int, list[int]]:
    linked: dict[int, list[int]] = {observation_id: [] for observation_id in observation_ids}
    if not observation_ids:
        return linked
    for observation_id, event_id in db.execute(
        select(EventObservation.observation_id, EventObservation.event_id)
        .join(Event, Event.id == EventObservation.event_id)
        .where(EventObservation.observation_id.in_(observation_ids))
        .order_by(Event.start_time, Event.id)
    ):
        linked[observation_id].append(event_id)
    return linked


def episode_links(db: Session, episode_ids: list[int]) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    """Event ids and representative observation ids for each episode."""

    events: dict[int, list[int]] = {episode_id: [] for episode_id in episode_ids}
    observations: dict[int, list[int]] = {episode_id: [] for episode_id in episode_ids}
    if not episode_ids:
        return events, observations
    for episode_id, event_id in db.execute(
        select(EpisodeEvent.episode_id, EpisodeEvent.event_id)
        .join(Event, Event.id == EpisodeEvent.event_id)
        .where(EpisodeEvent.episode_id.in_(episode_ids))
        .order_by(Event.start_time, Event.id)
    ):
        events[episode_id].append(event_id)
    for episode_id, observation_id in db.execute(
        select(EpisodeObservation.episode_id, EpisodeObservation.observation_id)
        .where(EpisodeObservation.episode_id.in_(episode_ids))
        .order_by(EpisodeObservation.observation_id)
    ):
        observations[episode_id].append(observation_id)
    return events, observations
