"""Small deterministic rules used by the proactive cue engine."""

from datetime import datetime, timedelta
import os


DEFAULT_COOLDOWN_MINUTES = 20
DEFAULT_OBJECT_LOOKBACK_MINUTES = 30
DEFAULT_RECOGNITION_WINDOW_MINUTES = 10
DEFAULT_SCHEDULE_LOOKAHEAD_MINUTES = 30

LEAVING_ACTIVITY_PREFIXES = (
    "preparing to leave",
    "getting ready to leave",
    "heading out",
    "going out",
    "leaving home",
)


def configured_minutes(name: str, default: int) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return float(default)
    return max(0.0, value)


def schedule_lookahead(now: datetime) -> datetime:
    return now + timedelta(minutes=configured_minutes("CUE_SCHEDULE_LOOKAHEAD_MINUTES", DEFAULT_SCHEDULE_LOOKAHEAD_MINUTES))


def cooldown_delta() -> timedelta:
    return timedelta(minutes=configured_minutes("CUE_COOLDOWN_MINUTES", DEFAULT_COOLDOWN_MINUTES))


def object_lookback_delta() -> timedelta:
    return timedelta(minutes=configured_minutes("CUE_OBJECT_LOOKBACK_MINUTES", DEFAULT_OBJECT_LOOKBACK_MINUTES))


def recognition_window_delta() -> timedelta:
    return timedelta(minutes=configured_minutes("CUE_RECOGNITION_WINDOW_MINUTES", DEFAULT_RECOGNITION_WINDOW_MINUTES))


def is_leaving_activity(activity: str | None) -> bool:
    normalized = " ".join((activity or "").casefold().rstrip(".").split())
    return any(normalized == prefix or normalized.startswith(f"{prefix} ") for prefix in LEAVING_ACTIVITY_PREFIXES)


def is_recent(value: datetime, now: datetime, window: timedelta) -> bool:
    return value <= now and now - value <= window
