"""Database configuration for the local SQLite-backed prototype."""

from collections.abc import Generator
import os

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///./memorycue.db"


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_database_engine(database_url: str) -> Engine:
    """Create an engine with SQLite integrity checks enabled for every connection."""

    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    database_engine = create_engine(database_url, connect_args=connect_args)
    if database_engine.dialect.name == "sqlite":
        event.listen(database_engine, "connect", _enable_sqlite_foreign_keys)
    return database_engine


engine = create_database_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class for the small set of application models."""


def init_db() -> None:
    """Create database tables if they do not exist yet."""

    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        memory_columns = {column["name"] for column in inspect(engine).get_columns("memories")}
        if "image_path" not in memory_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE memories ADD COLUMN image_path VARCHAR(255)"))


def get_db() -> Generator[Session, None, None]:
    """Provide one database session per request."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
