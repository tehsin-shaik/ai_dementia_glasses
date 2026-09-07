"""Provider-neutral interface for image understanding."""

from abc import ABC, abstractmethod

from .schemas import VisionAnalysis


class VisionAnalyzer(ABC):
    """Analyze one image and return only the app's normalized result."""

    @abstractmethod
    async def analyze_image(
        self,
        image_bytes: bytes,
        filename: str,
        context: str | None = None,
    ) -> VisionAnalysis:
        raise NotImplementedError
