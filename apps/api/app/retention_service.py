"""Retention for abandoned, unreviewed captures.

A capture nobody reviewed is deleted once it is older than the retention period
and nothing kept depends on it. Anything ambiguous is kept: reviewed data, a
capture linked to a Memory or reviewed copy, an Event or Episode that also
holds kept records, and any photo another kept record still points to.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import os

from fastapi import HTTPException
from sqlalchemy import Connection, Engine, delete, select
from sqlalchemy.orm import Session

from .database import advisory_lock
from .episode_service import CONSOLIDATION_LOCK_BASE
from .media_storage import safe_media_path
from .models import (
    Episode,
    EpisodeEvent,
    EpisodeObservation,
    Event,
    EventObservation,
    MediaBlob,
    Memory,
    MemoryEvent,
    MemoryObservation,
    Observation,
)

DEFAULT_RETENTION_HOURS = 168
MIN_RETENTION_HOURS = 24
logger = logging.getLogger(__name__)


class RetentionConfigError(ValueError):
    pass


def observation_retention() -> timedelta:
    """`OBSERVATION_RETENTION_HOURS`: a whole number of hours, at least 24 (default 168)."""

    raw = (os.getenv("OBSERVATION_RETENTION_HOURS") or "").strip()
    if not raw:
        return timedelta(hours=DEFAULT_RETENTION_HOURS)
    try:
        hours = int(raw)
    except ValueError as exc:
        raise RetentionConfigError("OBSERVATION_RETENTION_HOURS must be a whole number of hours.") from exc
    if hours < MIN_RETENTION_HOURS:
        raise RetentionConfigError(f"OBSERVATION_RETENTION_HOURS must be at least {MIN_RETENTION_HOURS}.")
    return timedelta(hours=hours)


@dataclass
class CleanupResult:
    examined: int = 0
    retained: int = 0
    deleted_observation_ids: list[int] = field(default_factory=list)
    deleted_events: int = 0
    deleted_episodes: int = 0
    deleted_media: list[str] = field(default_factory=list)
    retained_media: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _pairs(db: Session, statement) -> dict[int, set[int]]:
    grouped: dict[int, set[int]] = defaultdict(set)
    for key, value in db.execute(statement):
        grouped[key].add(value)
    return grouped


def _abandoned(db: Session, user_id: int, cutoff: datetime, result: CleanupResult):
    candidates = list(
        db.scalars(
            select(Observation)
            .where(
                Observation.user_id == user_id,
                Observation.reviewed.is_(False),
                Observation.created_at.is_not(None),
                Observation.created_at < cutoff,
            )
            .order_by(Observation.id)
            .with_for_update(skip_locked=True)
        )
    )
    result.examined = len(candidates)
    ids = {candidate.id for candidate in candidates}
    if not ids:
        return [], set(), set()

    reviewed_from = Observation.extra["reviewed_from_observation_id"].as_integer()
    blocked = set(db.scalars(select(MemoryObservation.observation_id).where(MemoryObservation.observation_id.in_(ids))))
    blocked |= set(db.scalars(select(reviewed_from).where(reviewed_from.in_(ids))))

    touching = select(EventObservation.event_id).where(EventObservation.observation_id.in_(ids))
    event_members = _pairs(
        db, select(EventObservation.event_id, EventObservation.observation_id).where(EventObservation.event_id.in_(touching))
    )
    event_ids = set(event_members)
    kept_events = {
        event_id
        for event_id, owner in db.execute(select(Event.id, Event.user_id).where(Event.id.in_(event_ids)))
        if owner != user_id
    }
    kept_events |= set(db.scalars(select(MemoryEvent.event_id).where(MemoryEvent.event_id.in_(event_ids))))
    episode_of = dict(db.execute(select(EpisodeEvent.event_id, EpisodeEvent.episode_id).where(EpisodeEvent.event_id.in_(event_ids))).tuples().all())

    episode_ids = set(episode_of.values()) | set(
        db.scalars(select(EpisodeObservation.episode_id).where(EpisodeObservation.observation_id.in_(ids)))
    )
    episode_events = _pairs(db, select(EpisodeEvent.episode_id, EpisodeEvent.event_id).where(EpisodeEvent.episode_id.in_(episode_ids)))
    episode_observations = _pairs(
        db, select(EpisodeObservation.episode_id, EpisodeObservation.observation_id).where(EpisodeObservation.episode_id.in_(episode_ids))
    )
    kept_episodes = {
        episode_id
        for episode_id, owner in db.execute(select(Episode.id, Episode.user_id).where(Episode.id.in_(episode_ids)))
        if owner != user_id
    }
    kept_episodes |= set(db.scalars(select(Memory.episode_id).where(Memory.episode_id.in_(episode_ids))))

    eligible = ids - blocked
    while True:
        events = {
            event_id
            for event_id in event_ids - kept_events
            if event_members[event_id] <= eligible
        }
        episodes = {
            episode_id
            for episode_id in episode_ids - kept_episodes
            if episode_events[episode_id] <= events and episode_observations[episode_id] <= eligible
        }
        events = {event_id for event_id in events if episode_of.get(event_id) in (None, *episodes)}
        still_needed = {item for event_id in event_ids - events for item in event_members[event_id]}
        still_needed |= {item for episode_id in episode_ids - episodes for item in episode_observations[episode_id]}
        if not eligible & still_needed:
            break
        eligible -= still_needed

    return [candidate for candidate in candidates if candidate.id in eligible], events, episodes


def _release_media(db: Session, user_id: int, filenames: set[str], result: CleanupResult) -> list[str]:
    """Delete this user's blobs no remaining record references; return local files that are safe to unlink."""

    if not filenames:
        return []
    referenced = set(db.scalars(select(Memory.image_path).where(Memory.image_path.in_(filenames))))
    referenced |= set(db.scalars(select(Observation.image_path).where(Observation.image_path.in_(filenames))))
    unlink: list[str] = []
    for filename in sorted(filenames):
        blob = db.get(MediaBlob, filename)
        if filename in referenced or (blob is not None and blob.user_id != user_id):
            result.retained_media.append(filename)
            continue
        if blob is not None:
            db.delete(blob)
        result.deleted_media.append(filename)
        unlink.append(filename)
    return unlink


def _unlink(filename: str, result: CleanupResult) -> None:
    try:
        path = safe_media_path(filename)
    except HTTPException:
        result.errors.append(f"{filename}: not a generated media filename")
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        result.errors.append(f"{filename}: {exc}")


def cleanup_abandoned_observations(db: Session, user_id: int, *, now: datetime | None = None) -> CleanupResult:
    """Delete one user's abandoned captures, their unshared events/episodes, and their unreferenced photos.

    Order: episode links and episodes, event links and events, observations, media rows; commit; then local files.
    Runs under the user's consolidation lock so it never races episode grouping or another cleanup.
    """

    cutoff = (now or datetime.now()) - observation_retention()
    result = CleanupResult()
    with advisory_lock(db, CONSOLIDATION_LOCK_BASE + user_id):
        try:
            observations, events, episodes = _abandoned(db, user_id, cutoff, result)
            observation_ids = [observation.id for observation in observations]
            if episodes:
                db.execute(delete(EpisodeObservation).where(EpisodeObservation.episode_id.in_(episodes)))
                db.execute(delete(EpisodeEvent).where(EpisodeEvent.episode_id.in_(episodes)))
                db.execute(delete(Episode).where(Episode.id.in_(episodes)))
            if events:
                db.execute(delete(EventObservation).where(EventObservation.event_id.in_(events)))
                db.execute(delete(Event).where(Event.id.in_(events)))
            if observation_ids:
                db.execute(delete(Observation).where(Observation.id.in_(observation_ids)))
            filenames = {observation.image_path for observation in observations if observation.image_path}
            unlink = _release_media(db, user_id, filenames, result)
            db.commit()
        except Exception:
            db.rollback()
            raise
    result.retained = result.examined - len(observation_ids)
    result.deleted_observation_ids = observation_ids
    result.deleted_events = len(events)
    result.deleted_episodes = len(episodes)
    for filename in unlink:
        _unlink(filename, result)
    return result


def cleanup_in_background(bind: Engine | Connection, user_id: int) -> None:
    """Run cleanup in its own session after a capture; a failure only postpones it to the next capture."""

    with Session(bind=bind) as db:
        try:
            cleanup_abandoned_observations(db, user_id)
        except Exception:
            db.rollback()
            logger.exception("Abandoned capture cleanup failed for user %s.", user_id)
