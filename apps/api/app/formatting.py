"""Shared presentation helpers for answers and recaps."""

from datetime import datetime

from .schemas import Language


def media_url(image_path: str | None) -> str | None:
    if image_path is None:
        return None
    return f"/api/media/{image_path}"


def format_time(value: datetime, language: Language = "en") -> str:
    formatted = value.strftime("%I:%M %p").lstrip("0")
    if language == "ar":
        return formatted.replace("AM", "صباحًا").replace("PM", "مساءً")
    return formatted
