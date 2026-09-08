"""Local face-recognition provider backed by dlib's pretrained ResNet encoder."""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from math import sqrt

from .base import (
    Embedding,
    FaceRecognizer,
    FaceRecognizerNotConfiguredError,
    MultipleFacesFoundError,
    NoFaceFoundError,
)


class LocalFaceRecognizer(FaceRecognizer):
    """Use dlib's local 128-dimensional face encoder on CPU."""

    def extract_embedding(self, image_bytes: bytes) -> Embedding:
        try:
            import numpy as np
            from PIL import Image, UnidentifiedImageError

            detector, predictor, encoder = _load_dlib_models()
            image = np.ascontiguousarray(Image.open(BytesIO(image_bytes)).convert("RGB"))
            locations = detector(image, 1)
        except FaceRecognizerNotConfiguredError:
            raise
        except ImportError as exc:
            raise FaceRecognizerNotConfiguredError(
                "Install the local dlib face-recognition dependencies to enable recognition."
            ) from exc
        except (OSError, UnidentifiedImageError) as exc:
            raise NoFaceFoundError("The image could not be read as a usable face image.") from exc

        if not locations:
            raise NoFaceFoundError("No usable face was found.")
        if len(locations) > 1:
            raise MultipleFacesFoundError(
                "Multiple faces were found. Please upload a photo containing one person."
            )

        try:
            shape = predictor(image, locations[0])
            encoding = encoder.compute_face_descriptor(image, shape)
        except Exception as exc:
            raise NoFaceFoundError("No usable face was found.") from exc
        return [float(value) for value in encoding]

    def compare(self, embedding_a: Embedding, embedding_b: Embedding) -> float:
        if len(embedding_a) != len(embedding_b) or not embedding_a:
            return 0.0
        distance = sqrt(sum((left - right) ** 2 for left, right in zip(embedding_a, embedding_b)))
        # dlib's encoding comparison uses Euclidean distance where lower is
        # better. Normalize it to a bounded similarity for larger-is-better
        # threshold and ambiguity decisions.
        return max(0.0, min(1.0, 1.0 - distance))


def get_face_recognizer() -> FaceRecognizer:
    """Construct the single configured local provider lazily."""

    return LocalFaceRecognizer()


@lru_cache(maxsize=1)
def _load_dlib_models():
    try:
        import dlib
        from face_recognition_models import (
            face_recognition_model_location,
            pose_predictor_five_point_model_location,
        )
        return (
            dlib.get_frontal_face_detector(),
            dlib.shape_predictor(pose_predictor_five_point_model_location()),
            dlib.face_recognition_model_v1(face_recognition_model_location()),
        )
    except (ImportError, OSError) as exc:
        raise FaceRecognizerNotConfiguredError(
            "Install the local dlib face-recognition dependencies to enable recognition."
        ) from exc
