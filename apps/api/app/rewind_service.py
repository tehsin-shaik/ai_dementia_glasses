"""Chronological recaps built only from saved, reviewed moments."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .correction_service import latest_correction
from .formatting import format_time, media_url
from .models import Episode, Memory
from .schemas import Language, RewindMoment, RewindResponse

DEFAULT_WINDOW_MINUTES = 10
MAX_MOMENTS = 3


def moment_source(memory: Memory) -> str:
    """A saved photo means the wearer captured it; seeded rows have none."""

    return "capture" if memory.image_path else "sample"


def to_moment(db: Session, memory: Memory) -> RewindMoment:
    correction = latest_correction(db, memory.id)
    episode = db.get(Episode, memory.episode_id) if memory.episode_id else None
    return RewindMoment(
        memory_id=memory.id,
        recorded_at=memory.timestamp,
        location=memory.location,
        activity=memory.activity or None,
        description=memory.description,
        image_url=media_url(memory.image_path),
        source=moment_source(memory),
        corrected_at=correction[0] if correction else None,
        corrected_by=correction[1] if correction else None,
        episode_id=episode.id if episode else None,
        episode_title=episode.title if episode else None,
    )


def recent_memories(db: Session, user_id: int, since: datetime | None, limit: int) -> list[Memory]:
    statement = select(Memory).where(Memory.user_id == user_id)
    if since is not None:
        statement = statement.where(Memory.timestamp >= since)
    statement = statement.order_by(Memory.timestamp.desc(), Memory.id.desc()).limit(limit)
    return list(db.scalars(statement))


def moment_phrase(moment: RewindMoment, language: Language) -> str:
    detail = moment.activity or moment.description.rstrip(".")
    recorded = format_time(moment.recorded_at, language)
    if language == "ar":
        return f"الساعة {recorded} في {moment.location}: {detail}."
    return f"At {recorded} in {moment.location}: {detail}."


def build_summary(moments: list[RewindMoment], language: Language) -> str:
    count = len(moments)
    if language == "ar":
        header = f"هذه {count} من اللحظات المحفوظة، وليست تسجيلًا متواصلًا."
    else:
        noun = "moment" if count == 1 else "moments"
        header = f"These are {count} saved {noun}, not continuous recording."
    return " ".join([header, *(moment_phrase(moment, language) for moment in moments)])


def empty_summary(window_minutes: int, has_earlier: bool, language: Language) -> str:
    if language == "ar":
        message = f"لا توجد لحظات محفوظة في آخر {window_minutes} دقيقة."
        if has_earlier:
            message += " يمكنك عرض لحظات محفوظة أقدم."
        return message
    message = f"No moments were saved in the last {window_minutes} minutes."
    if has_earlier:
        message += " You can show earlier saved moments."
    return message


def build_rewind(
    db: Session,
    user_id: int,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    include_earlier: bool = False,
    language: Language = "en",
    now: datetime | None = None,
) -> RewindResponse:
    """Recap the newest saved moments, never describing old ones as recent."""

    current_time = now or datetime.now()
    since = current_time - timedelta(minutes=window_minutes)
    in_window = recent_memories(db, user_id, since, MAX_MOMENTS)
    has_earlier = (
        db.scalar(
            select(Memory.id)
            .where(Memory.user_id == user_id, Memory.timestamp < since)
            .limit(1)
        )
        is not None
    )

    memories = in_window
    within_window = bool(in_window)
    if not in_window and include_earlier:
        memories = recent_memories(db, user_id, None, MAX_MOMENTS)

    moments = [to_moment(db, memory) for memory in reversed(memories)]
    summary = (
        build_summary(moments, language)
        if moments
        else empty_summary(window_minutes, has_earlier, language)
    )
    return RewindResponse(
        summary=summary,
        moments=moments,
        window_minutes=window_minutes,
        within_window=within_window,
        has_earlier=has_earlier,
        language=language,
    )
