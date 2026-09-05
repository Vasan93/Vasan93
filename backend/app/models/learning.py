"""Weakness profile, puzzle attempts, spaced-repetition cards and lessons."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Weakness(Base):
    """One taxonomy key tracked for one user, with accumulated evidence."""

    __tablename__ = "weaknesses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    taxonomy_key: Mapped[str] = mapped_column(String(48), index=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | improving | retired
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="weaknesses")  # noqa: F821


class PuzzleAttempt(Base):
    __tablename__ = "puzzle_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    puzzle_id: Mapped[str] = mapped_column(String(32), index=True)
    weakness_key: Mapped[str | None] = mapped_column(String(48), nullable=True)
    context: Mapped[str] = mapped_column(String(16), default="training")  # assessment | training | lesson
    correct: Mapped[bool] = mapped_column(default=False)
    played_move: Mapped[str] = mapped_column(String(12), default="")
    time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SrsCard(Base):
    """SM-2 card. One per active weakness per user."""

    __tablename__ = "srs_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    weakness_key: Mapped[str] = mapped_column(String(48), index=True)
    ease: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[float] = mapped_column(Float, default=0.0)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    successes: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    topic: Mapped[str] = mapped_column(String(48), index=True)
    language: Mapped[str] = mapped_column(String(32), default="English")
    transcript: Mapped[str] = mapped_column(Text)  # JSON: sections, worked examples, checks
    comprehension_checks: Mapped[str] = mapped_column(Text, default="[]")  # JSON
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
