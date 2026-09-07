"""Deterministic intent matching and grounded answer generation."""

from datetime import date, datetime, time
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Memory, ObjectObservation, Person, ScheduleItem, User
from .schemas import Intent, QueryResponse


def normalize_question(question: str) -> str:
    """Normalize punctuation and whitespace for exact intent matching."""

    normalized = re.sub(r"[^a-z0-9\s]", " ", question.lower())
    return " ".join(normalized.split())


def detect_intent(question: str) -> Intent:
    normalized = normalize_question(question)
    if normalized == "what was i doing":
        return "recent_activity"
    if normalized in {"where are my keys", "where did i leave my keys"}:
        return "object_location"
    if normalized == "who is sarah":
        return "person_lookup"
    if normalized == "what am i doing today":
        return "schedule"
    return "unknown"


def unknown_response() -> QueryResponse:
    return QueryResponse(answer="I don't know that yet.", intent="unknown", source_ids=[])


def format_time(value: datetime) -> str:
    return value.strftime("%I:%M %p").lstrip("0")


def answer_question(db: Session, question: str) -> QueryResponse:
    intent = detect_intent(question)
    if intent == "unknown":
        return unknown_response()

    user = db.scalar(select(User).order_by(User.id).limit(1))
    if user is None:
        return unknown_response()

    if intent == "recent_activity":
        memory = db.scalar(
            select(Memory)
            .where(Memory.user_id == user.id)
            .where(Memory.activity.is_not(None))
            .where(Memory.activity != "")
            .order_by(Memory.timestamp.desc(), Memory.id.desc())
            .limit(1)
        )
        if memory is None:
            return unknown_response()
        return QueryResponse(
            answer=f"You were {memory.activity.rstrip('.')}.",
            intent=intent,
            source_ids=[f"memory:{memory.id}"],
        )

    if intent == "object_location":
        observation = db.scalar(
            select(ObjectObservation)
            .where(
                ObjectObservation.user_id == user.id,
                ObjectObservation.object_name == "keys",
            )
            .order_by(ObjectObservation.observed_at.desc(), ObjectObservation.id.desc())
            .limit(1)
        )
        if observation is None:
            return unknown_response()
        return QueryResponse(
            answer=(
                f"I last saw your keys on the {observation.location} "
                f"at {format_time(observation.observed_at)}."
            ),
            intent=intent,
            source_ids=[
                f"object_observation:{observation.id}",
                f"memory:{observation.memory_id}",
            ],
        )

    if intent == "person_lookup":
        person = db.scalar(
            select(Person)
            .where(Person.user_id == user.id, Person.name.ilike("sarah"))
            .limit(1)
        )
        if person is None:
            return unknown_response()
        return QueryResponse(
            answer=f"{person.name} is your {person.relationship.lower()}.",
            intent=intent,
            source_ids=[f"person:{person.id}"],
        )

    today_start = datetime.combine(date.today(), time.min)
    tomorrow_start = datetime.combine(date.today(), time.max)
    schedule_items = list(
        db.scalars(
            select(ScheduleItem)
            .where(
                ScheduleItem.user_id == user.id,
                ScheduleItem.scheduled_at >= today_start,
                ScheduleItem.scheduled_at <= tomorrow_start,
            )
            .order_by(ScheduleItem.scheduled_at, ScheduleItem.id)
        )
    )
    if not schedule_items:
        return unknown_response()
    schedule_phrases = []
    for item in schedule_items:
        verb = "is at" if item.title.casefold() == "dinner" else "at"
        schedule_phrases.append(f"{item.title} {verb} {format_time(item.scheduled_at)}.")
    answer = " ".join(schedule_phrases)
    return QueryResponse(
        answer=answer,
        intent=intent,
        source_ids=[f"schedule_item:{item.id}" for item in schedule_items],
    )
