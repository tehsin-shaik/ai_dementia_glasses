"""Small abstraction around the local face embedding implementation."""

from abc import ABC, abstractmethod
from typing import TypeAlias


Embedding: TypeAlias = list[float]


class FaceRecognizerError(RuntimeError):
    """Base error for local face recognition failures."""


class FaceRecognizerNotConfiguredError(FaceRecognizerError):
    """The optional local recognition dependency is not installed or configured."""


class NoFaceFoundError(FaceRecognizerError):
    """The image does not contain exactly one usable face."""


class MultipleFacesFoundError(FaceRecognizerError):
    """The image contains more than one face and cannot be enrolled safely."""


class FaceRecognizer(ABC):
    """Provider contract used by enrollment and patient recognition routes."""

    @abstractmethod
    def extract_embedding(self, image_bytes: bytes) -> Embedding:
        raise NotImplementedError

    @abstractmethod
    def compare(self, embedding_a: Embedding, embedding_b: Embedding) -> float:
        """Return a normalized similarity where larger values are better."""

        raise NotImplementedError
