"""The single configured vision provider used by the MVP."""

import base64
import json
import os
from typing import Any

import httpx
from pydantic import ValidationError

from ..media_storage import media_type_for
from .base import VisionAnalyzer
from .schemas import VisionAnalysis


class VisionProviderNotConfiguredError(RuntimeError):
    """Raised when image understanding is intentionally disabled."""


class VisionProviderError(RuntimeError):
    """Raised when the configured provider cannot return a valid analysis."""


VISION_INSTRUCTIONS = """You analyze one image for an assistive memory support prototype.
Describe only what is visibly supported by the image. Return concise, factual details that
could help the user remember an everyday moment. Use null when a location or activity is not
clear. List useful visible objects and their visible location when clear. Use confidence only
when useful, as a number from 0 to 1; otherwise use null.

Do not guess or infer names, relationships, medical conditions, diagnoses, emotions, hidden
objects, or facts outside the image. Do not identify people. Do not claim an object is present
when it is uncertain. Do not include explanations or chain-of-thought; return only the requested
structured result."""


VISION_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "description": {"type": "string"},
        "location": {"type": ["string", "null"]},
        "activity": {"type": ["string", "null"]},
        "objects": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "location": {"type": ["string", "null"]},
                    "confidence": {"type": ["number", "null"]},
                },
                "required": ["name", "location", "confidence"],
            },
        },
    },
    "required": ["description", "location", "activity", "objects"],
}


class OpenAIVisionAnalyzer(VisionAnalyzer):
    """Use OpenAI's multimodal Responses API without exposing provider data to the app."""

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def analyze_image(
        self,
        image_bytes: bytes,
        filename: str,
        context: str | None = None,
    ) -> VisionAnalysis:
        media_type = media_type_for(filename)
        encoded_image = base64.b64encode(image_bytes).decode("ascii")
        context_instruction = (
            f"\nOptional user context (use only to focus the description, never to invent facts): {context}"
            if context
            else ""
        )
        payload = {
            "model": self.model,
            "instructions": VISION_INSTRUCTIONS,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Analyze this image and return the normalized memory suggestion."
                                f"{context_instruction}"
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:{media_type};base64,{encoded_image}",
                        },
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "memorycue_vision_analysis",
                    "strict": True,
                    "schema": VISION_RESPONSE_SCHEMA,
                }
            },
            "store": False,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/responses",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise VisionProviderError("The vision provider could not be reached.") from exc

        if response.is_error:
            raise VisionProviderError("The vision provider rejected the image.")

        try:
            response_payload = response.json()
            content = extract_response_text(response_payload)
            return VisionAnalysis.model_validate(json.loads(content))
        except (ValueError, TypeError, KeyError, IndexError, ValidationError) as exc:
            raise VisionProviderError("The vision provider returned an invalid analysis.") from exc


def extract_response_text(response_payload: dict[str, Any]) -> str:
    """Extract structured output text without passing provider internals to callers."""

    if not isinstance(response_payload, dict):
        raise ValueError("Provider response was not an object")

    output_text = response_payload.get("output_text")
    if isinstance(output_text, str) and output_text:
        return output_text

    for output_item in response_payload.get("output", []):
        if not isinstance(output_item, dict) or output_item.get("type") != "message":
            continue
        for content_item in output_item.get("content", []):
            if (
                isinstance(content_item, dict)
                and content_item.get("type") == "output_text"
                and isinstance(content_item.get("text"), str)
            ):
                return content_item["text"]

    raise ValueError("Missing provider output text")


def get_vision_analyzer() -> VisionAnalyzer:
    """Build the configured analyzer, or report that the optional feature is disabled."""

    provider = (os.getenv("VISION_PROVIDER") or "").strip().casefold()
    api_key = (os.getenv("VISION_API_KEY") or "").strip()
    model = (os.getenv("VISION_MODEL") or "").strip()

    if not provider or not api_key or not model:
        raise VisionProviderNotConfiguredError
    if provider != "openai":
        raise VisionProviderError("The configured vision provider is not supported.")

    return OpenAIVisionAnalyzer(api_key=api_key, model=model)
