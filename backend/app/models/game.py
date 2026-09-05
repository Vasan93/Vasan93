"""Imported and played games, plus their move-by-move engine analysis."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    pgn: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16))  # imported | practice | assessment
    result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    white: Mapped[str | None] = mapped_column(String(120), nullable=True)
    black: Mapped[str | None] = mapped_column(String(120), nullable=True)
    user_color: Mapped[str] = mapped_column(String(5), default="white")  # white | black
    played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | running | done | failed
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="games")  # noqa: F821
    moves: Mapped[list["AnalyzedMove"]] = relationship(
        back_populates="game", cascade="all, delete-orphan", order_by="AnalyzedMove.ply"
    )


class AnalyzedMove(Base):
    """One analyzed ply. Every field here is engine output, never LLM output."""

    __tablename__ = "analyzed_moves"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    ply: Mapped[int] = mapped_column(Integer)
    move_number: Mapped[int] = mapped_column(Integer)
    side: Mapped[str] = mapped_column(String(5))  # white | black
    fen: Mapped[str] = mapped_column(String(120))  # position BEFORE the move
    played_move: Mapped[str] = mapped_column(String(12))  # SAN
    best_move: Mapped[str] = mapped_column(String(12))  # SAN
    best_line: Mapped[str] = mapped_column(String(255), default="")  # SAN principal variation
    eval_cp_before: Mapped[int] = mapped_column(Integer)
    eval_cp_after: Mapped[int] = mapped_column(Integer)
    cp_loss: Mapped[int] = mapped_column(Integer)
    win_prob_loss: Mapped[float] = mapped_column(Float, default=0.0)
    move_label: Mapped[str] = mapped_column(String(16))  # best | good | inaccuracy | mistake | blunder
    detected_motif: Mapped[str | None] = mapped_column(String(48), nullable=True)
    taxonomy_keys: Mapped[str] = mapped_column(String(255), default="")  # comma-separated weakness keys

    game: Mapped[Game] = relationship(back_populates="moves")
