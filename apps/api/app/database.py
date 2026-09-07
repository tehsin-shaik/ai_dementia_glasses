"""Database configuration for the local SQLite-backed prototype."""

from collections.abc import Generator
import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///./memorycue.db"
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
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
