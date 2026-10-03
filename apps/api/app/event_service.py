"""Conservative interpretation of observations into events.

Rules here only fire on explicit evidence (a stored object, a caregiver-entered
person, a stated location, or several matching cue words), and every event
records its confidence and the rule that produced it.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Event, EventObservation, Observation

CONTEXT_WINDOW = timedelta(minutes=30)
CONTEXT_LIMIT = 10
MIN_OBJECT_CONFIDENCE = 0.6
LOCATION_CHANGE_CONFIDENCE = 0.6
PERSON_CONFIDENCE = 0.7


@dataclass(frozen=True)
class ActivityRule:
    name: str
    title: str
    cues: frozenset[str]
    min_cues: int
    locations: frozenset[str] = frozenset()
    before: time | None = None


ACTIVITY_RULES = (
    ActivityRule(
        name="preparing_breakfast",
        title="Preparing breakfast",
        cues=frozenset({"refrigerator", "fridge", "eggs", "egg", "stove", "pan", "toast", "cereal", "toaster"}),
        min_cues=2,
        locations=frozenset({"kitchen"}),
        before=time(11, 0),
    ),
    ActivityRule(
        name="preparing_food",
        title="Preparing food",
        cues=frozenset({"refrigerator", "fridge", "eggs", "egg", "stove", "pan", "toast", "cereal", "toaster", "pot", "cooking"}),
        min_cues=2,
        locations=frozenset({"kitchen"}),
    ),
    ActivityRule(
        name="leaving_home",
        title="Getting ready to leave",
        cues=frozenset({"keys", "wallet", "coat", "jacket", "shoes", "bag", "leave", "leaving", "door"}),
        min_cues=2,
    ),
)


def _words(text: str | None) -> set[str]:
    return set(re.findall(r"[a-z]+", (text or "").casefold()))


def _location_words(observation: Observation) -> set[str]:
    return _words(observation.location_label)


def _cue_words(observation: Observation) -> set[str]:
    words = _words(observation.description) | _words(observation.activity)
    for entry in observation.detected_objects or []:
        words |= _words(entry.get("name"))
    return words


def _new_event(observation: Observation, **fields) -> Event:
    fields.setdefault("location", observation.location_label)
    return Event(
        user_id=observation.user_id,
        start_time=observation.timestamp,
        created_at=datetime.now(),
        **fields,
    )


def link(db: Session, event: Event, observations: list[Observation]) -> Event:
    db.add(event)
    db.flush()
    for observation in observations:
        db.add(EventObservation(event_id=event.id, observation_id=observation.id))
    db.flush()
    return event


def context_observations(db: Session, observation: Observation) -> list[Observation]:
    """The same user's observations shortly before this one, oldest first."""

    rows = db.scalars(
        select(Observation)
        .where(
            Observation.user_id == observation.user_id,
            Observation.id != observation.id,
            Observation.timestamp <= observation.timestamp,
            Observation.timestamp >= observation.timestamp - CONTEXT_WINDOW,
        )
        .order_by(Observation.timestamp.desc(), Observation.id.desc())
        .limit(CONTEXT_LIMIT)
    )
    return list(reversed(list(rows)))


def reviewed_events(db: Session, observation: Observation) -> list[Event]:
    """Events for a moment the wearer reviewed: what they confirmed, nothing more."""

    events: list[Event] = []
    title = observation.activity or observation.description
    if title:
        events.append(
            link(
                db,
                _new_event(
                    observation,
                    event_type="recorded_activity",
                    title=title[:200],
                    description=observation.description,
                    confidence=1.0,
                    inference="reviewed",
                    people=list(observation.detected_people or []),
                    objects=list(observation.detected_objects or []),
                ),
                [observation],
            )
        )
    for entry in observation.detected_objects or []:
        where = entry.get("location") or observation.location_label
        events.append(
            link(
                db,
                _new_event(
                    observation,
                    event_type="object_seen",
                    title=f"{entry['name']} seen" + (f" on the {where}" if where else ""),
                    description=None,
                    confidence=1.0,
                    inference="reviewed",
                    location=where,
                    objects=[entry],
                ),
                [observation],
            )
        )
    return events


def observed_events(db: Session, observation: Observation, context: list[Observation]) -> list[Event]:
    """Events supported by a single unreviewed observation and its recent context."""

    events: list[Event] = []
    previous = context[-1] if context else None
    if (
        previous is not None
        and observation.location_label
        and previous.location_label
        and observation.location_label.casefold() != previous.location_label.casefold()
    ):
        events.append(
            link(
                db,
                _new_event(
                    observation,
                    event_type="entered_location",
                    title=f"Entered {observation.location_label}",
                    description=f"Previously observed in {previous.location_label}.",
                    confidence=LOCATION_CHANGE_CONFIDENCE,
                    inference="rule:location_change",
                ),
                [previous, observation],
            )
        )
    for entry in observation.detected_objects or []:
        confidence = entry.get("confidence")
        if confidence is None or confidence < MIN_OBJECT_CONFIDENCE:
            continue
        where = entry.get("location") or observation.location_label
        events.append(
            link(
                db,
                _new_event(
                    observation,
                    event_type="object_seen",
                    title=f"{entry['name']} seen" + (f" on the {where}" if where else ""),
                    description=None,
                    confidence=float(confidence),
                    inference="rule:object_detected",
                    location=where,
                    objects=[entry],
                ),
                [observation],
            )
        )
    for person in observation.detected_people or []:
        if person.get("person_id") is None:
            continue
        events.append(
            link(
                db,
                _new_event(
                    observation,
                    event_type="person_seen",
                    title=f"Saw {person['name']}",
                    description=None,
                    confidence=PERSON_CONFIDENCE,
                    inference="rule:known_person",
                    people=[person],
                ),
                [observation],
            )
        )
    return events


def activity_events(db: Session, observation: Observation, context: list[Observation]) -> list[Event]:
    """At most one themed activity, only when several cue words agree."""

    window = [*context, observation]
    cues: set[str] = set()
    for item in window:
        cues |= _cue_words(item)
    for rule in ACTIVITY_RULES:
        if rule.before is not None and observation.timestamp.time() >= rule.before:
            continue
        if rule.locations and not rule.locations & _location_words(observation):
            continue
        matched = cues & rule.cues
        if len(matched) < rule.min_cues:
            continue
        existing = db.scalar(
            select(Event).where(
                Event.user_id == observation.user_id,
                Event.inference == f"rule:{rule.name}",
                Event.start_time >= observation.timestamp - CONTEXT_WINDOW,
                Event.start_time <= observation.timestamp,
            )
        )
        if existing is not None:
            existing.end_time = max(existing.end_time or existing.start_time, observation.timestamp)
            db.add(EventObservation(event_id=existing.id, observation_id=observation.id))
            db.flush()
            return [existing]
        supporting = [item for item in window if _cue_words(item) & rule.cues]
        start = supporting[0]
        event = _new_event(
            observation,
            event_type="activity",
            title=rule.title,
            description=f"Inferred from: {', '.join(sorted(matched))}.",
            confidence=min(0.8, 0.4 + 0.1 * len(matched)),
            inference=f"rule:{rule.name}",
        )
        event.start_time = start.timestamp
        event.end_time = observation.timestamp if observation.timestamp != start.timestamp else None
        return [link(db, event, supporting)]
    return []


def generate_events(db: Session, observations: list[Observation]) -> list[Event]:
    """Interpret a batch of observations (for example the last N) into events."""

    events: list[Event] = []
    for observation in sorted(observations, key=lambda item: (item.timestamp, item.id)):
        events.extend(events_for_observation(db, observation))
    return events


def events_for_observation(db: Session, observation: Observation) -> list[Event]:
    already_linked = db.scalar(
        select(EventObservation.event_id).where(EventObservation.observation_id == observation.id).limit(1)
    )
    if already_linked is not None:
        return []
    context = context_observations(db, observation)
    if observation.reviewed:
        events = reviewed_events(db, observation)
    else:
        events = observed_events(db, observation, context)
    return [*events, *activity_events(db, observation, context)]
