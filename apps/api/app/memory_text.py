"""Canonical one-line text for each memory layer, ready to be embedded later."""

from datetime import datetime

from .formatting import format_time
from .models import Episode, Event, Memory, Observation


def _names(entries: list | None) -> list[str]:
    return [str(entry["name"]) for entry in entries or [] if isinstance(entry, dict) and entry.get("name")]


def _join(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _when(start: datetime, end: datetime | None = None) -> str:
    day = start.strftime("%Y-%m-%d")
    if end is None or end == start:
        return f"On {day} at {format_time(start)}"
    return f"On {day} from {format_time(start)} to {format_time(end)}"


def _sentence(*parts: str | None) -> str:
    return " ".join(part.strip().rstrip(".") + "." for part in parts if part and part.strip())


def observation_to_text(observation: Observation) -> str:
    where = f" in {observation.location_label}" if observation.location_label else ""
    people = _names(observation.detected_people)
    objects = _names(observation.detected_objects)
    return _sentence(
        f"{_when(observation.timestamp)}{where} ({observation.source})",
        observation.activity,
        observation.description,
        f"People: {_join(people)}" if people else None,
        f"Objects: {_join(objects)}" if objects else None,
        f'Said: "{observation.transcript}"' if observation.transcript else None,
    )


def event_to_text(event: Event) -> str:
    where = f" in {event.location}" if event.location else ""
    people = _names(event.people)
    return _sentence(
        f"{_when(event.start_time, event.end_time)}{where}: {event.title}",
        event.description if event.description != event.title else None,
        f"With {_join(people)}" if people else None,
    )


def episode_to_text(episode: Episode) -> str:
    where = f" in {episode.location}" if episode.location else ""
    people = _names(episode.people)
    return _sentence(
        f"{_when(episode.start_time, episode.end_time)}{where}: {episode.title}",
        episode.summary,
        f"With {_join(people)}" if people else None,
    )


def memory_to_text(memory: Memory) -> str:
    people = _names(memory.people)
    objects = _names(memory.objects)
    return _sentence(
        f"{_when(memory.timestamp, memory.end_time)} in {memory.location}",
        memory.activity,
        memory.description,
        f"People: {_join(people)}" if people else None,
        f"Objects: {_join(objects)}" if objects else None,
    )
