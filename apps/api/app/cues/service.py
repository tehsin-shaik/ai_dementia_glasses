"""Explainable, patient-scoped proactive cue evaluation."""

from datetime import datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import CueState, ImportantObject, Memory, ObjectObservation, Person, RecognitionEvent, ScheduleItem
from ..query_service import format_time
from .rules import (
    cooldown_delta,
    is_leaving_activity,
    is_recent,
    object_lookback_delta,
    recognition_window_delta,
    schedule_lookahead,
)
from .schemas import ProactiveCue


def _cue_is_suppressed(state: CueState | None, now: datetime) -> bool:
    if state is None:
        return False
    if state.dismissed_at is not None:
        return True
    return state.last_shown_at is not None and now - state.last_shown_at < cooldown_delta()


def _upsert_state(db: Session, user_id: int, cue_key: str) -> CueState:
    state = db.scalar(
        select(CueState).where(CueState.user_id == user_id, CueState.cue_key == cue_key)
    )
    if state is None:
        state = CueState(user_id=user_id, cue_key=cue_key)
        db.add(state)
    return state


class CueEngine:
    """Evaluate and record only conservative context cues."""

    def evaluate(self, db: Session, user_id: int, now: datetime | None = None) -> list[ProactiveCue]:
        current_time = now or datetime.now()
        states = {
            state.cue_key: state
            for state in db.scalars(select(CueState).where(CueState.user_id == user_id))
        }
        candidates = [
            *self._recognized_person_cues(db, user_id, current_time),
            *self._schedule_cues(db, user_id, current_time),
            *self._important_object_cues(db, user_id, current_time),
        ]
        candidates.sort(key=lambda cue: (-cue.priority, cue.id))
        return [cue for cue in candidates if not _cue_is_suppressed(states.get(cue.id), current_time)]

    def mark_presented(self, db: Session, user_id: int, cue_id: str, now: datetime | None = None) -> None:
        state = _upsert_state(db, user_id, cue_id)
        state.last_shown_at = now or datetime.now()

    def dismiss(self, db: Session, user_id: int, cue_id: str, now: datetime | None = None) -> None:
        state = _upsert_state(db, user_id, cue_id)
        state.dismissed_at = now or datetime.now()

    def _schedule_cues(self, db: Session, user_id: int, now: datetime) -> list[ProactiveCue]:
        today_start = datetime.combine(now.date(), time.min)
        today_end = datetime.combine(now.date(), time.max)
        lookahead = schedule_lookahead(now)
        items = db.scalars(
            select(ScheduleItem)
            .where(
                ScheduleItem.user_id == user_id,
                ScheduleItem.scheduled_at >= today_start,
                ScheduleItem.scheduled_at <= today_end,
                ScheduleItem.scheduled_at >= now,
                ScheduleItem.scheduled_at <= lookahead,
            )
            .order_by(ScheduleItem.scheduled_at, ScheduleItem.id)
        )
        return [
            ProactiveCue(
                id=f"schedule:{item.id}",
                type="schedule_upcoming",
                title="Coming up",
                message=f"{item.title} at {format_time(item.scheduled_at)}.",
                priority=50,
                source_ids=[f"schedule:{item.id}"],
                expires_at=item.scheduled_at,
            )
            for item in items
        ]

    def _recognized_person_cues(self, db: Session, user_id: int, now: datetime) -> list[ProactiveCue]:
        event_and_person = db.execute(
            select(RecognitionEvent, Person)
            .join(Person, Person.id == RecognitionEvent.person_id)
            .where(
                RecognitionEvent.user_id == user_id,
                Person.user_id == user_id,
                RecognitionEvent.recognized_at >= now - recognition_window_delta(),
                RecognitionEvent.recognized_at <= now,
            )
            .order_by(RecognitionEvent.recognized_at.desc(), RecognitionEvent.id.desc())
            .limit(1)
        ).first()
        if event_and_person is None:
            return []

        event, person = event_and_person
        message = f"Your {person.relationship.lower()}."
        today_end = datetime.combine(now.date(), time.max)
        matching_schedule = db.scalar(
            select(ScheduleItem)
            .where(
                ScheduleItem.user_id == user_id,
                ScheduleItem.scheduled_at <= today_end,
                ScheduleItem.scheduled_at >= now,
                ScheduleItem.scheduled_at <= schedule_lookahead(now),
                func.lower(ScheduleItem.title).contains(person.name.casefold()),
            )
            .order_by(ScheduleItem.scheduled_at, ScheduleItem.id)
            .limit(1)
        )
        if matching_schedule is not None:
            message += f" {matching_schedule.title} at {format_time(matching_schedule.scheduled_at)}."
        source_ids = [f"person:{person.id}", f"recognition_event:{event.id}"]
        expires_at = event.recognized_at + recognition_window_delta()
        if matching_schedule is not None:
            source_ids.append(f"schedule:{matching_schedule.id}")
            expires_at = min(expires_at, matching_schedule.scheduled_at)
        return [
            ProactiveCue(
                id=f"person:{person.id}:recognition:{event.id}:{event.recognized_at.isoformat(timespec='seconds')}",
                type="recognized_person",
                title=person.name,
                message=message,
                priority=100,
                source_ids=source_ids,
                expires_at=expires_at,
            )
        ]

    def _important_object_cues(self, db: Session, user_id: int, now: datetime) -> list[ProactiveCue]:
        cues: list[ProactiveCue] = []
        for important_object in db.scalars(
            select(ImportantObject).where(ImportantObject.user_id == user_id).order_by(ImportantObject.id)
        ):
            observation_and_memory = db.execute(
                select(ObjectObservation, Memory)
                .join(Memory, Memory.id == ObjectObservation.memory_id)
                .where(
                    ObjectObservation.user_id == user_id,
                    Memory.user_id == user_id,
                    func.lower(ObjectObservation.object_name) == important_object.name.casefold(),
                )
                .order_by(ObjectObservation.observed_at.desc(), ObjectObservation.id.desc())
                .limit(1)
            ).first()
            if observation_and_memory is None:
                continue
            observation, memory = observation_and_memory
            if not is_recent(memory.timestamp, now, object_lookback_delta()):
                continue
            if observation.observed_at > memory.timestamp or not is_leaving_activity(memory.activity):
                continue
            cues.append(
                ProactiveCue(
                    id=f"object:{important_object.id}:observation:{observation.id}",
                    type="important_object",
                    title=important_object.name,
                    message=f"Last seen at {observation.location}.",
                    priority=25,
                    source_ids=[
                        f"important_object:{important_object.id}",
                        f"object_observation:{observation.id}",
                        f"memory:{memory.id}",
                    ],
                    expires_at=memory.timestamp + object_lookback_delta(),
                )
            )
        return cues
