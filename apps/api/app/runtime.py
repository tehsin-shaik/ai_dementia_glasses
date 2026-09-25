"""Deployment-time configuration for hosted demo environments."""

from collections.abc import Iterator
from contextlib import contextmanager
import os

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .models import User
from .seed import seed_demo_data


LOCAL_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
SEED_LOCK_ID = 8412557301


def allowed_origins() -> list[str]:
    """Return the local development origins plus any configured deployed origins."""

    configured = os.getenv("ALLOWED_ORIGINS", "")
    extra = [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]
    return LOCAL_ORIGINS + [origin for origin in extra if origin not in LOCAL_ORIGINS]


@contextmanager
def _seed_lock(db: Session) -> Iterator[None]:
    """Serialize seeding so concurrent cold starts cannot duplicate the demo data."""

    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        yield
        return
    # The lock lives on its own connection so the seeding commits cannot release it.
    with bind.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": SEED_LOCK_ID})
        connection.commit()
        try:
            yield
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": SEED_LOCK_ID}
            )
            connection.commit()


def seed_if_empty(db: Session) -> bool:
    """Insert demo data when the database has no users yet.

    Serverless instances start from an empty database, so the demo profiles have
    to exist before the first request reaches them.
    """

    with _seed_lock(db):
        if db.scalar(select(func.count()).select_from(User)):
            return False
        seed_demo_data(db)
        return True
