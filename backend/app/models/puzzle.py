"""The puzzle bank (seeded from the Lichess open puzzle database, CC0)."""
from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Puzzle(Base):
    __tablename__ = "puzzles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    fen: Mapped[str] = mapped_column(String(120))
    solution_moves: Mapped[str] = mapped_column(String(255))  # space-separated UCI, opponent replies included
    themes: Mapped[str] = mapped_column(String(255), default="")  # space-separated Lichess themes
    taxonomy_keys: Mapped[str] = mapped_column(String(255), default="")  # space-separated weakness keys
    rating: Mapped[int] = mapped_column(Integer, index=True)
    popularity: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(32), default="lichess")
