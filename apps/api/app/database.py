"""Database configuration for SQLite locally and Postgres in hosted demos."""

from collections.abc import Generator, Iterator
from contextlib import contextmanager
import os

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool


def normalize_database_url(database_url: str) -> str:
    """Point the bare `postgres`/`postgresql` schemes at the installed psycopg driver."""

    for prefix in ("postgres://", "postgresql://"):
        if database_url.startswith(prefix):
            return "postgresql+psycopg://" + database_url[len(prefix) :]
    return database_url


DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL") or "sqlite:///./memorycue.db")


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_database_engine(database_url: str) -> Engine:
    """Create an engine with SQLite integrity checks enabled for every connection."""

    database_url = normalize_database_url(database_url)
    if database_url.startswith("sqlite"):
        database_engine = create_engine(database_url, connect_args={"check_same_thread": False})
        event.listen(database_engine, "connect", _enable_sqlite_foreign_keys)
        return database_engine
    # Serverless instances are frozen between requests, so pooled connections go stale.
    return create_engine(database_url, poolclass=NullPool, pool_pre_ping=True)


engine = create_database_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class for the small set of application models."""


def init_db() -> None:
    """Create database tables if they do not exist yet; see migrations for upgrades."""

    Base.metadata.create_all(bind=engine)


@contextmanager
def advisory_lock(db: Session, lock_id: int) -> Iterator[None]:
    """Serialize work across concurrent cold starts on Postgres; a no-op on SQLite."""

    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        yield
        return
    # The lock lives on its own connection so commits inside the block cannot release it.
    with bind.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": lock_id})
        connection.commit()
        try:
            yield
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})
            connection.commit()


def get_db() -> Generator[Session, None, None]:
    """Provide one database session per request."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
