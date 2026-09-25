"""Deterministic intent matching and grounded answer generation."""

from datetime import date, datetime, time, timedelta
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .correction_service import latest_correction
from .formatting import format_time, media_url
from .models import ImportantObject, Memory, ObjectObservation, Person, ScheduleItem
from .schemas import Intent, Language, QueryEvidence, QueryResponse


ARABIC_OBJECT_SYNONYMS = {
    "مفاتيح": "keys",
    "مفاتيحي": "keys",
    "المفاتيح": "keys",
    "نظارة": "glasses",
    "نظارتي": "glasses",
    "محفظة": "wallet",
    "محفظتي": "wallet",
    "هاتف": "phone",
    "هاتفي": "phone",
    "جوال": "phone",
    "جوالي": "phone",
}

SCHEDULE_TERMS_EN = {"today", "schedule", "plans", "plan", "appointments"}
SCHEDULE_TERMS_AR = {"اليوم", "جدول", "جدولي", "مواعيدي", "برنامجي"}
ACTIVITY_TERMS_EN = {"doing", "do", "did", "was"}
ACTIVITY_TERMS_AR = {"أفعل", "افعل", "كنت", "نشاطي"}
LOCATION_TERMS_EN = {"where", "find", "seen", "misplaced", "lost", "leave", "left", "put"}
LOCATION_TERMS_AR = {"أين", "اين", "وين"}
NEGATION_TERMS = {"not", "except", "besides", "ليس", "وليس"}
PERSON_TRAILING_WORDS = {"again", "please", "now", "to", "me", "مرة", "أخرى"}
PERSON_TERMS_AR = ("من هي", "من هو", "من تكون", "من يكون")

STOP_WORDS = {
    "where", "are", "is", "my", "the", "did", "i", "leave", "put", "last",
    "see", "seen", "have", "a", "an", "of", "do", "you", "know", "can",
    "find", "left", "placed", "was", "were", "me", "tell", "what", "on",
    "in", "at", "أين", "اين", "وين", "هي", "هو", "ما", "هل", "لي",
}


def normalize_question(question: str) -> str:
    """Normalize punctuation and whitespace for intent matching.

    Arabic letters are preserved so bilingual questions normalize consistently.
    """

    normalized = re.sub(r"[^\w\s]", " ", question.lower(), flags=re.UNICODE)
    return " ".join(normalized.split())


def detect_intent(question: str) -> Intent:
    """Classify a question without needing database context."""

    normalized = normalize_question(question)
    tokens = set(normalized.split())
    if not normalized:
        return "unknown"

    # A locating question is about an object even when it also mentions today.
    if tokens & LOCATION_TERMS_EN or tokens & LOCATION_TERMS_AR:
        return "object_location"

    if tokens & SCHEDULE_TERMS_EN or tokens & SCHEDULE_TERMS_AR:
        return "schedule"

    if "what" in tokens and tokens & ACTIVITY_TERMS_EN:
        return "recent_activity"
    if tokens & ACTIVITY_TERMS_AR and ("ماذا" in tokens or "ما" in tokens):
        return "recent_activity"

    if normalized.startswith("who is") or normalized.startswith("whos"):
        return "person_lookup"
    if any(normalized.startswith(prefix) for prefix in PERSON_TERMS_AR):
        return "person_lookup"

    return "unknown"


def unknown_response(language: Language = "en") -> QueryResponse:
    answer = (
        "لا أملك معلومات محفوظة عن ذلك، ولن أخمّن."
        if language == "ar"
        else "I couldn't find matching saved information for that."
    )
    return QueryResponse(
        answer=answer,
        intent="unknown",
        source_ids=[],
        evidence=[],
        language=language,
    )


def candidate_object_names(question: str) -> list[str]:
    """Return the words of a question that could name a stored object.

    Words after a negation such as "not my keys" are excluded so an excluded
    object never becomes the answer.
    """

    words = normalize_question(question).split()
    for index, word in enumerate(words):
        if word in NEGATION_TERMS:
            words = words[:index]
            break
    tokens = [token for token in words if token not in STOP_WORDS]
    candidates: list[str] = []
    for token in tokens:
        candidates.append(ARABIC_OBJECT_SYNONYMS.get(token, token))
    # A trailing singular form lets "where is my key" match a stored "keys".
    for token in list(candidates):
        if token.endswith("s"):
            candidates.append(token[:-1])
        else:
            candidates.append(f"{token}s")
    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


def known_object_names(db: Session, user_id: int) -> set[str]:
    observed = db.scalars(
        select(ObjectObservation.object_name).where(ObjectObservation.user_id == user_id).distinct()
    )
    important = db.scalars(
        select(ImportantObject.name).where(ImportantObject.user_id == user_id).distinct()
    )
    return {name.casefold() for name in observed} | {name.casefold() for name in important}


def resolve_object_name(db: Session, user_id: int, question: str) -> str | None:
    known = known_object_names(db, user_id)
    for candidate in candidate_object_names(question):
        if candidate in known:
            return candidate
    return None


def resolve_person_name(question: str) -> str | None:
    """Return the full name asked about, so a longer name is not truncated."""

    normalized = normalize_question(question)
    match = re.match(r"(?:who is|whos|من هي|من هو|من تكون|من يكون)\s+(.+)", normalized)
    if match is None:
        return None
    words = match.group(1).split()
    while words and words[-1] in PERSON_TRAILING_WORDS:
        words.pop()
    return " ".join(words) or None


def answer_question(
    db: Session,
    user_id: int,
    question: str,
    language: Language = "en",
) -> QueryResponse:
    intent = detect_intent(question)
    if intent == "unknown":
        return unknown_response(language)

    if intent == "recent_activity":
        memory = db.scalar(
            select(Memory)
            .where(Memory.user_id == user_id)
            .where(Memory.activity.is_not(None))
            .where(Memory.activity != "")
            .order_by(Memory.timestamp.desc(), Memory.id.desc())
            .limit(1)
        )
        if memory is None:
            return unknown_response(language)
        activity = memory.activity.rstrip(".")
        answer = (
            f"آخر ما كنت تفعله: {activity}."
            if language == "ar"
            else f"You were {activity}."
        )
        return QueryResponse(
            answer=answer,
            intent=intent,
            source_ids=[f"memory:{memory.id}"],
            evidence=[
                QueryEvidence(
                    source_id=f"memory:{memory.id}",
                    label=f"Saved memory #{memory.id}",
                    detail=memory.location,
                    recorded_at=memory.timestamp,
                    image_url=media_url(memory.image_path),
                )
            ],
            language=language,
        )

    if intent == "object_location":
        object_name = resolve_object_name(db, user_id, question)
        if object_name is None:
            return unknown_response(language)
        observation = db.scalar(
            select(ObjectObservation)
            .where(
                ObjectObservation.user_id == user_id,
                ObjectObservation.object_name == object_name,
            )
            .order_by(ObjectObservation.observed_at.desc(), ObjectObservation.id.desc())
            .limit(1)
        )
        if observation is None:
            return unknown_response(language)
        observation_memory = db.get(Memory, observation.memory_id)
        observation_photo = (
            media_url(observation_memory.image_path) if observation_memory else None
        )
        correction = latest_correction(db, observation.memory_id)
        observed_time = format_time(observation.observed_at, language)
        answer = (
            f"آخر تسجيل: {object_name} في {observation.location} الساعة {observed_time}."
            if language == "ar"
            else f"Last recorded: your {object_name} on the {observation.location} at {observed_time}."
        )
        return QueryResponse(
            answer=answer,
            intent=intent,
            source_ids=[
                f"object_observation:{observation.id}",
                f"memory:{observation.memory_id}",
            ],
            evidence=[
                QueryEvidence(
                    source_id=f"object_observation:{observation.id}",
                    label=f"Observation of {object_name}",
                    detail=observation.location,
                    recorded_at=observation.observed_at,
                    image_url=observation_photo,
                    corrected_at=correction[0] if correction else None,
                    corrected_by=correction[1] if correction else None,
                ),
                QueryEvidence(
                    source_id=f"memory:{observation.memory_id}",
                    label=f"Saved memory #{observation.memory_id}",
                    detail=observation.location,
                    recorded_at=observation.observed_at,
                    image_url=observation_photo,
                    corrected_at=correction[0] if correction else None,
                    corrected_by=correction[1] if correction else None,
                ),
            ],
            language=language,
        )

    if intent == "person_lookup":
        person_name = resolve_person_name(question)
        if person_name is None:
            return unknown_response(language)
        person = db.scalar(
            select(Person)
            .where(Person.user_id == user_id, Person.name.ilike(person_name))
            .order_by(Person.id)
            .limit(1)
        )
        if person is None:
            return unknown_response(language)
        answer = (
            f"{person.name}: {person.relationship} — حسب السجل المحفوظ لدى مقدّم الرعاية."
            if language == "ar"
            else f"{person.name} is your {person.relationship.lower()}."
        )
        return QueryResponse(
            answer=answer,
            intent=intent,
            source_ids=[f"person:{person.id}"],
            evidence=[
                QueryEvidence(
                    source_id=f"person:{person.id}",
                    label="Caregiver-entered person",
                    detail=f"{person.name} · {person.relationship}",
                    recorded_at=None,
                )
            ],
            language=language,
        )

    today_start = datetime.combine(date.today(), time.min)
    tomorrow_start = datetime.combine(date.today() + timedelta(days=1), time.min)
    schedule_items = list(
        db.scalars(
            select(ScheduleItem)
            .where(
                ScheduleItem.user_id == user_id,
                ScheduleItem.scheduled_at >= today_start,
                ScheduleItem.scheduled_at < tomorrow_start,
            )
            .order_by(ScheduleItem.scheduled_at, ScheduleItem.id)
        )
    )
    if not schedule_items:
        return unknown_response(language)
    schedule_phrases = []
    for item in schedule_items:
        if language == "ar":
            schedule_phrases.append(f"{item.title} الساعة {format_time(item.scheduled_at, language)}.")
            continue
        verb = "is at" if item.title.casefold() == "dinner" else "at"
        schedule_phrases.append(f"{item.title} {verb} {format_time(item.scheduled_at)}.")
    answer = " ".join(schedule_phrases)
    return QueryResponse(
        answer=answer,
        intent=intent,
        source_ids=[f"schedule_item:{item.id}" for item in schedule_items],
        evidence=[
            QueryEvidence(
                source_id=f"schedule_item:{item.id}",
                label="Caregiver-entered schedule",
                detail=item.title,
                recorded_at=item.scheduled_at,
            )
            for item in schedule_items
        ],
        language=language,
    )
