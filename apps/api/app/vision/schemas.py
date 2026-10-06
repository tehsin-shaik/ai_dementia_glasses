"""Strict internal schemas for normalized vision results."""

from pydantic import BaseModel, ConfigDict, Field


class DetectedObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    location: str | None = Field(default=None, max_length=120)
    confidence: float | None = Field(default=None, ge=0, le=1)


class VisionAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=500)
    location: str | None = Field(default=None, max_length=120)
    activity: str | None = Field(default=None, max_length=200)
    objects: list[DetectedObject] = Field(default_factory=list, max_length=20)


MIN_OBJECT_CONFIDENCE = 0.4


def _clean(value: str | None) -> str | None:
    cleaned = " ".join((value or "").split())
    return cleaned or None


def normalize_analysis(analysis: VisionAnalysis) -> VisionAnalysis:
    """Keep a provider suggestion to what it reported with reasonable confidence.

    Blank fields become null, objects below `MIN_OBJECT_CONFIDENCE` are
    dropped, duplicate names are merged, and the most confident objects come
    first. Objects without a confidence keep their original order after them.
    """

    seen: set[str] = set()
    objects: list[DetectedObject] = []
    for item in analysis.objects:
        name = _clean(item.name)
        if name is None or name.casefold() in seen:
            continue
        if item.confidence is not None and item.confidence < MIN_OBJECT_CONFIDENCE:
            continue
        seen.add(name.casefold())
        objects.append(DetectedObject(name=name, location=_clean(item.location), confidence=item.confidence))
    objects.sort(key=lambda item: -(item.confidence if item.confidence is not None else -1.0))
    return VisionAnalysis(
        description=_clean(analysis.description) or "No clear description was returned.",
        location=_clean(analysis.location),
        activity=_clean(analysis.activity),
        objects=objects,
    )
