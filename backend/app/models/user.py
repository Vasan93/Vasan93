"""User accounts and their rating history."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(80))
    preferred_language: Mapped[str] = mapped_column(String(32), default="English")
    current_rating_estimate: Mapped[int] = mapped_column(Integer, default=1000)
    goal: Mapped[str] = mapped_column(String(500), default="")
    assessment_completed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    rating_history: Mapped[list["RatingHistory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="RatingHistory.recorded_at"
    )
    games: Mapped[list["Game"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # noqa: F821
    weaknesses: Mapped[list["Weakness"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # noqa: F821


class RatingHistory(Base):
    __tablename__ = "rating_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(32))  # assessment | puzzles | practice | import
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="rating_history")
