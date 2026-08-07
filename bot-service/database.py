"""Database module: SQLAlchemy models, session and init helper."""

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

load_dotenv()

Base = declarative_base()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://calendarix:password@postgres:5432/calendarix",
)

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def utcnow() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


class Source(Base):
    """A Telegram channel added by a user."""

    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    url = Column(String, nullable=False)
    title = Column(String, nullable=False)
    type = Column(String, default="telegram")
    is_active = Column(Boolean, default=True)
    added_at = Column(DateTime, default=utcnow)

    events = relationship("Event", back_populates="source")


class Event(Base):
    """An event extracted from a channel post."""

    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(
        Integer, ForeignKey("sources.id"), nullable=False, index=True
    )
    user_id = Column(Integer, nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    event_date = Column(DateTime, nullable=False, index=True)
    location = Column(String, nullable=True)
    original_text = Column(Text, nullable=False)
    post_url = Column(String, nullable=False)
    is_confirmed = Column(Boolean, default=False)
    extracted_at = Column(DateTime, default=utcnow)

    source = relationship("Source", back_populates="events")


def init_db() -> None:
    """Create all tables if they do not exist yet."""
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Tables created (or already exist)")
    except Exception as exc:
        print(f"❌ Failed to create tables: {exc}")
        raise
