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
