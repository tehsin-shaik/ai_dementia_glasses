"""Group events into episodes.

Consolidation is separate from capture: it runs after the response (as a
background task), on demand, or periodically, so saving a moment never waits
on it. It is idempotent: each event joins at most one episode.
"""

from collections import Counter
from datetime import datetime, timedelta
import logging

from sqlalchemy import Connection, Engine, func, select
from sqlalchemy.orm import Session

from .database import advisory_lock
from .event_service import REVIEWED_INFERENCES
from .formatting import format_time
from .models import (
    Episode,
    EpisodeEvent,
    EpisodeObservation,
    Event,
    EventObservation,
    Memory,
    MemoryEvent,
    Observation,
)

EPISODE_GAP = timedelta(minutes=20)
REPRESENTATIVE_LIMIT = 3
CONSOLIDATION_LOCK_BASE = 8_412_600_000_000
logger = logging.getLogger(__name__)


def _event_end(event: Event) -> datetime:
    return event.end_time or event.start_time


def episode_events(db: Session, episode_id: int) -> list[Event]:
    return list(
        db.scalars(
            select(Event)
            .join(EpisodeEvent, EpisodeEvent.event_id == Event.id)
            .where(EpisodeEvent.episode_id == episode_id)
            .order_by(Event.start_time, Event.id)
        )
    )


def unassigned_events(db: Session, user_id: int) -> list[Event]:
    assigned = select(EpisodeEvent.event_id)
    return list(
        db.scalars(
            select(Event)
            .where(Event.user_id == user_id, Event.id.not_in(assigned))
            .order_by(Event.start_time, Event.id)
        )
    )


def _distance(episode: Episode, moment: datetime) -> timedelta:
    end = episode.end_time or episode.start_time
    if moment < episode.start_time:
        return episode.start_time - moment
    if moment > end:
        return moment - end
    return timedelta(0)


def episode_for(db: Session, event: Event) -> Episode | None:
    """The nearest episode whose span, widened by the gap, covers the event's start.

    Ties go to the earlier episode, so the same events always group the same way.
    """

    candidates = db.scalars(
        select(Episode)
        .where(
            Episode.user_id == event.user_id,
            Episode.start_time <= event.start_time + EPISODE_GAP,
            func.coalesce(Episode.end_time, Episode.start_time) >= event.start_time - EPISODE_GAP,
        )
        .order_by(Episode.start_time, Episode.id)
    )
    return min(candidates, key=lambda episode: _distance(episode, event.start_time), default=None)


def _merge_named(entries: list[list | None]) -> list[dict]:
    merged: dict[str, dict] = {}
    for group in entries:
        for entry in group or []:
            if isinstance(entry, dict) and entry.get("name"):
                merged.setdefault(str(entry["name"]).casefold(), entry)
    return list(merged.values())


def _join(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


def describe(events: list[Event]) -> tuple[str, str, float]:
    """Title, inference label, and confidence for a group of events."""

    themed = [event for event in events if event.event_type == "activity"]
    if themed:
        best = max(themed, key=lambda event: (event.confidence, event.start_time))
        return best.title, best.inference, best.confidence
    locations: list[str] = []
    for event in events:
        if event.location and event.location.casefold() not in {item.casefold() for item in locations}:
            locations.append(event.location)
    title = f"Moments in {_join(locations)}" if locations else "Saved moments"
    confidence = round(sum(event.confidence for event in events) / len(events), 2)
    return title, "locations", confidence


def summarize(events: list[Event]) -> str:
    """The episode's events in order, using their own titles only."""

    parts = [
        f"{format_time(event.start_time)} {event.title.rstrip('.')}"
        for event in events
        if event.event_type != "activity"
    ]
    return "; ".join(parts) + "." if parts else ""


def refresh_episode(db: Session, episode: Episode) -> Episode:
    events = episode_events(db, episode.id)
    if not events:
        return episode
    episode.start_time = events[0].start_time
    last_evidence = max(_event_end(event) for event in events)
    episode.end_time = last_evidence if last_evidence != episode.start_time else None
    episode.title, episode.inference, episode.confidence = describe(events)
    episode.summary = summarize(events)
    location_counts = Counter(event.location for event in events if event.location)
    episode.location = location_counts.most_common(1)[0][0] if location_counts else None
    episode.people = _merge_named([event.people for event in events])
    episode.objects = _merge_named([event.objects for event in events])
    episode.updated_at = datetime.now()

    event_ids = [event.id for event in events]
    observations = list(
        db.scalars(
            select(Observation)
            .where(
                Observation.id.in_(
                    select(EventObservation.observation_id).where(EventObservation.event_id.in_(event_ids))
                )
            )
            .order_by(Observation.timestamp, Observation.id)
        )
    )
    with_images = [item for item in observations if item.image_path]
    representative = (with_images or observations)[:REPRESENTATIVE_LIMIT]
    existing = set(
        db.scalars(select(EpisodeObservation.observation_id).where(EpisodeObservation.episode_id == episode.id))
    )
    for observation in representative:
        if observation.id not in existing:
            db.add(EpisodeObservation(episode_id=episode.id, observation_id=observation.id))

    memories = db.scalars(
        select(Memory)
        .join(MemoryEvent, MemoryEvent.memory_id == Memory.id)
        .where(MemoryEvent.event_id.in_(event_ids))
    )
    for memory in memories:
        memory.episode_id = episode.id
    db.flush()
    return episode


def consolidate_episodes(db: Session, user_id: int) -> list[Episode]:
    """Attach every unassigned event to a nearby episode or start a new one."""

    touched: dict[int, Episode] = {}
    for event in unassigned_events(db, user_id):
        episode = episode_for(db, event)
        if episode is None:
            episode = Episode(
                user_id=user_id,
                start_time=event.start_time,
                end_time=None,
                title=event.title,
                summary="",
                inference="locations",
                confidence=event.confidence,
                created_at=datetime.now(),
            )
            db.add(episode)
            db.flush()
        db.add(EpisodeEvent(episode_id=episode.id, event_id=event.id))
        db.flush()
        # Keep the span current so the next event in this pass can join it.
        episode.start_time = min(episode.start_time, event.start_time)
        episode.end_time = max(episode.end_time or episode.start_time, _event_end(event))
        touched[episode.id] = episode
    for episode in touched.values():
        refresh_episode(db, episode)
    return list(touched.values())


def consolidate_and_commit(db: Session, user_id: int) -> list[Episode]:
    """Consolidate and commit while holding a per-user lock, so concurrent runs cannot double-assign events."""

    with advisory_lock(db, CONSOLIDATION_LOCK_BASE + user_id):
        episodes = consolidate_episodes(db, user_id)
        db.commit()
    return episodes


def consolidate_in_background(bind: Engine | Connection, user_id: int) -> None:
    """Run consolidation in its own session, e.g. from a FastAPI background task.

    Captures are already committed; a failure here only leaves events ungrouped until the next run.
    """

    with Session(bind=bind) as db:
        try:
            consolidate_and_commit(db, user_id)
        except Exception:
            db.rollback()
            logger.exception("Episode consolidation failed for user %s.", user_id)


def grounded_episode_titles(db: Session, user_id: int, episode_ids: set[int]) -> dict[int, str]:
    """Wearer-facing episode labels built only from reviewed or legacy saved events.

    Rule-inferred and unreviewed events still shape `Episode.title` for timelines,
    but never the label shown next to saved moments or spoken answers.
    """

    if not episode_ids:
        return {}
    grouped: dict[int, list[Event]] = {}
    for episode_id, event in db.execute(
        select(EpisodeEvent.episode_id, Event)
        .join(Event, Event.id == EpisodeEvent.event_id)
        .where(
            EpisodeEvent.episode_id.in_(episode_ids),
            Event.user_id == user_id,
            Event.inference.in_(REVIEWED_INFERENCES),
        )
        .order_by(Event.start_time, Event.id)
    ):
        grouped.setdefault(episode_id, []).append(event)
    return {episode_id: describe(events)[0] for episode_id, events in grouped.items()}
