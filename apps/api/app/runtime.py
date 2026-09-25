"""Deployment-time configuration for hosted demo environments."""

import os

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import User
from .seed import seed_demo_data


LOCAL_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


def allowed_origins() -> list[str]:
    """Return the local development origins plus any configured deployed origins."""

    configured = os.getenv("ALLOWED_ORIGINS", "")
    extra = [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]
    return LOCAL_ORIGINS + [origin for origin in extra if origin not in LOCAL_ORIGINS]


def seed_if_empty(db: Session) -> bool:
    """Insert demo data when the database has no users yet.

    Serverless instances start from an empty writable disk, so the demo profiles
    have to be recreated before the first request reaches them.
    """

    if db.scalar(select(func.count()).select_from(User)):
        return False
    seed_demo_data(db)
    return True
