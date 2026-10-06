"""Deterministic intent matching and grounded answer generation."""

from datetime import date, datetime, time, timedelta
import re

from sqlalchemy.orm import Session

from .correction_service import latest_correction
from .episode_service import grounded_episode_titles
from .formatting import format_time, media_url
from .models import Memory
from .retrieval_service import (
    find_person,
    known_object_names,
    latest_activity_memory,
    latest_object_observation,
    memories_for_day,
    schedule_for_day,
)
from .schemas import Intent, Language, QueryEvidence, QueryResponse
from .spoken_time import mentions_a_clock_time, rewrite_spoken_times


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

SCHEDULE_TERMS_EN = {"schedule", "plans", "plan", "appointments", "appointment", "calendar"}
SCHEDULE_TERMS_AR = {"جدول", "جدولي", "مواعيدي", "موعدي", "برنامجي"}
OPEN_QUESTION_STARTS = {"what", "whats", "ماذا", "ما", "شو"}
# Advice, obligation, and future wording is not a request for a saved past moment.
NON_RECALL_TERMS = {
    "should", "supposed", "need", "needs", "must", "next", "will", "gonna", "going",
    "يجب", "المفروض", "سأفعل", "سوف", "لازم",
}
ACTIVITY_TERMS_EN = {"doing", "do"}
ACTIVITY_TERMS_AR = {"أفعل", "افعل", "كنت", "نشاطي"}
LOCATION_TERMS_EN = {"where", "find", "seen", "misplaced", "lost", "leave", "left", "put"}
LOCATION_TERMS_AR = {"أين", "اين", "وين"}
NEGATION_TERMS = {"not", "except", "besides", "ليس", "وليس"}
PERSON_TRAILING_WORDS = {"again", "please", "now", "to", "me", "مرة", "أخرى"}
PERSON_TERMS_AR = ("من هي", "من هو", "من تكون", "من يكون")

PAST_TENSE_TERMS = {"was", "did", "كنت"}
DAY_SUMMARY_VERBS = {"did", "فعلت"}
TODAY_TERMS = {"today", "اليوم"}
CLOCK_TIME_PATTERN = re.compile(
    r"(?:\b(?:at|around|about)\s+|الساع[ةه]\s*)?"
    r"(?<!\d)(\d{1,2})(?::(\d{2}))?\s*"
    r"(a\.?\s?m\.?|p\.?\s?m\.?|صباحًا|صباحا|ص|مساءً|مساء|م)?(?!\w)",
    flags=re.IGNORECASE,
)
ACTIVITY_LOOKBACK = timedelta(minutes=30)

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


def clock_time_mention(question: str) -> tuple[int, int] | None:
    """Return the (hour, minute) asked about, as in "What was I doing at 10:10 AM?".

    Spoken times ("ten thirty AM", "الساعة العاشرة") are first rewritten to
    digits. A bare number only counts when it is introduced by
    "at"/"around"/"الساعة" or has minutes or AM/PM, so stray numbers are not
    read as times. Values are not range-checked here.
    """

    for match in CLOCK_TIME_PATTERN.finditer(rewrite_spoken_times(question)):
        text, hour_text, minute_text, meridiem = match.group(0), match.group(1), match.group(2), match.group(3)
        introduced = not text.lstrip()[:1].isdigit()
        if not (introduced or minute_text or meridiem):
            continue
        hour = int(hour_text)
        minute = int(minute_text or 0)
        marker = (meridiem or "").replace(".", "").replace(" ", "").casefold()
        if marker in {"pm", "مساءً", "مساء", "م"} and 1 <= hour < 12:
            hour += 12
        elif marker in {"am", "صباحًا", "صباحا", "ص"} and hour == 12:
            hour = 0
        return hour, minute
    return None


def requested_clock_time(question: str) -> time | None:
    mention = clock_time_mention(question)
    if mention is None or mention[0] > 23 or mention[1] > 59:
        return None
    return time(*mention)


def asks_about_a_clock_time(question: str) -> bool:
    """Whether the question names a clock time, even one that cannot be resolved."""

    return clock_time_mention(question) is not None or mentions_a_clock_time(rewrite_spoken_times(question))


def detect_intent(question: str) -> Intent:
    """Classify a question without needing database context."""

    normalized = normalize_question(question)
    tokens = set(normalized.split())
    if not normalized:
        return "unknown"

    # A locating question is about an object even when it also mentions today.
    if tokens & LOCATION_TERMS_EN or tokens & LOCATION_TERMS_AR:
        return "object_location"

    asks_about_activity = bool(tokens & ACTIVITY_TERMS_EN or tokens & ACTIVITY_TERMS_AR)
    is_open_question = bool(tokens & OPEN_QUESTION_STARTS)
    if tokens & PAST_TENSE_TERMS and asks_about_activity and asks_about_a_clock_time(question):
        return "time_anchored_activity"

    # "What did I do today?" asks about the past; "What am I doing today?" is the schedule.
    if is_open_question and tokens & DAY_SUMMARY_VERBS and tokens & TODAY_TERMS:
        return "today_recall"

    if tokens & SCHEDULE_TERMS_EN or tokens & SCHEDULE_TERMS_AR:
        return "schedule"
    # A yes/no question that mentions today ("Did I take my medicine today?") is not a schedule request.
    if is_open_question and tokens & TODAY_TERMS and not tokens & PAST_TENSE_TERMS:
        return "schedule"

    if tokens & NON_RECALL_TERMS:
        return "unknown"
    if ("what" in tokens and tokens & ACTIVITY_TERMS_EN) or (
        tokens & ACTIVITY_TERMS_AR and ("ماذا" in tokens or "ما" in tokens)
    ):
        return "time_anchored_activity" if asks_about_a_clock_time(question) else "recent_activity"

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

    if intent in ("recent_activity", "time_anchored_activity"):
        asked_time = requested_clock_time(question)
        if asked_time is None and asks_about_a_clock_time(question):
            return unknown_response(language)
        asked_at = datetime.combine(date.today(), asked_time) if asked_time is not None else None
        # The moment in progress at the asked time: the latest saved one at or shortly before it.
        memory = latest_activity_memory(
            db, user_id, at=asked_at, lookback=ACTIVITY_LOOKBACK if asked_at is not None else None
        )
        if memory is None:
            return unknown_response(language)
        activity = memory.activity.rstrip(".")
        activity_correction = latest_correction(db, memory.id)
        answer = activity_answer(activity, memory.timestamp, asked_time, language)
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
                    corrected_at=activity_correction[0] if activity_correction else None,
                    corrected_by=activity_correction[1] if activity_correction else None,
                )
            ],
            language=language,
        )

    if intent == "object_location":
        object_name = resolve_object_name(db, user_id, question)
        if object_name is None:
            return unknown_response(language)
        observation = latest_object_observation(db, user_id, object_name)
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
        person = find_person(db, user_id, person_name)
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

    if intent == "today_recall":
        return day_summary(db, user_id, language)

    schedule_items = schedule_for_day(db, user_id, date.today())
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


def activity_answer(activity: str, saved_at: datetime, asked_time: time | None, language: Language) -> str:
    """Report a saved moment with its own time, never as what is happening now.

    The activity text is quoted after a colon so stored phrasing of any shape
    reads correctly.
    """

    saved_time = format_time(saved_at, language)
    if asked_time is None:
        if language == "ar":
            return f"آخر لحظة محفوظة، الساعة {saved_time}: {activity}."
        return f"Your last saved moment, at {saved_time}: {activity}."
    if (saved_at.hour, saved_at.minute) == (asked_time.hour, asked_time.minute):
        if language == "ar":
            return f"لحظة محفوظة الساعة {saved_time}: {activity}."
        return f"Saved at {saved_time}: {activity}."
    asked = format_time(datetime.combine(saved_at.date(), asked_time), language)
    if language == "ar":
        return f"أقرب لحظة محفوظة قبل الساعة {asked} كانت الساعة {saved_time}: {activity}."
    return f"The closest saved moment before {asked} was at {saved_time}: {activity}."


def day_summary(db: Session, user_id: int, language: Language = "en") -> QueryResponse:
    """Today's saved moments in order, grouped by the episode each belongs to."""

    memories = memories_for_day(db, user_id, date.today())
    if not memories:
        return unknown_response(language)
    episode_titles = grounded_episode_titles(db, user_id, {memory.episode_id for memory in memories if memory.episode_id})
    phrases = [
        f"{(memory.activity or memory.description).rstrip('.')} ({format_time(memory.timestamp, language)})"
        for memory in memories
    ]
    if language == "ar":
        answer = f"لحظاتك المحفوظة اليوم: {'، '.join(phrases)}."
    else:
        count = len(memories)
        noun = "moment" if count == 1 else "moments"
        answer = f"Today you saved {count} {noun}: {'; '.join(phrases)}."
    evidence: list[QueryEvidence] = []
    for memory in memories:
        correction = latest_correction(db, memory.id)
        evidence.append(
            QueryEvidence(
                source_id=f"memory:{memory.id}",
                label=f"Saved memory #{memory.id}",
                detail=memory.location,
                recorded_at=memory.timestamp,
                image_url=media_url(memory.image_path),
                corrected_at=correction[0] if correction else None,
                corrected_by=correction[1] if correction else None,
            )
        )
    episode_memories: dict[int, list[Memory]] = {}
    for memory in memories:
        if memory.episode_id in episode_titles:
            episode_memories.setdefault(memory.episode_id, []).append(memory)
    for episode_id, members in sorted(episode_memories.items(), key=lambda item: (item[1][0].timestamp, item[0])):
        evidence.append(
            QueryEvidence(
                source_id=f"episode:{episode_id}",
                label=f"Episode (grouped automatically): {episode_titles[episode_id]}",
                detail=", ".join(dict.fromkeys(member.location for member in members)),
                recorded_at=members[0].timestamp,
            )
        )
    return QueryResponse(
        answer=answer,
        intent="today_recall",
        source_ids=[item.source_id for item in evidence],
        evidence=evidence,
        language=language,
    )
