"""Patient-scoped matching and conservative threshold configuration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from .base import Embedding, FaceRecognizer


DEFAULT_MATCH_THRESHOLD = 0.65
DEFAULT_MATCH_MARGIN = 0.08


@dataclass(frozen=True)
class MatchCandidate:
    person_id: int
    embedding: Embedding


@dataclass(frozen=True)
class MatchDecision:
    person_id: int | None
    confidence: float


def _configured_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(0.0, min(1.0, value))


def match_threshold() -> float:
    return _configured_float("FACE_MATCH_THRESHOLD", DEFAULT_MATCH_THRESHOLD)


def match_margin() -> float:
    return _configured_float("FACE_MATCH_MARGIN", DEFAULT_MATCH_MARGIN)


def serialize_embedding(embedding: Embedding) -> str:
    return json.dumps(embedding, separators=(",", ":"))


def deserialize_embedding(value: str) -> Embedding:
    parsed = json.loads(value)
    if not isinstance(parsed, list) or not parsed or not all(isinstance(item, (int, float)) for item in parsed):
        raise ValueError("Stored face embedding has an invalid shape.")
    return [float(item) for item in parsed]


def choose_match(
    query_embedding: Embedding,
    candidates: list[MatchCandidate],
    recognizer: FaceRecognizer,
) -> MatchDecision:
    if not candidates:
        return MatchDecision(person_id=None, confidence=0.0)

    ranked = sorted(
        (
            recognizer.compare(query_embedding, candidate.embedding),
            candidate.person_id,
        )
        for candidate in candidates
    )
    ranked.reverse()
    best_score, best_person_id = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else None

    if best_score < match_threshold():
        return MatchDecision(person_id=None, confidence=best_score)
    if second_score is not None and best_score - second_score < match_margin():
        return MatchDecision(person_id=None, confidence=best_score)
    return MatchDecision(person_id=best_person_id, confidence=best_score)
