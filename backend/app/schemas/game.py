"""Game import and playback payloads."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Platform = Literal["lichess", "chess.com"]
Color = Literal["white", "black"]


class PgnImportRequest(BaseModel):
    pgn: str = Field(min_length=2, max_length=512_000)
    user_color: Color | None = None
    player_name: str | None = Field(default=None, max_length=120)


class UsernameImportRequest(BaseModel):
    platform: Platform
    username: str = Field(min_length=1, max_length=64)
    max_games: int = Field(default=5, ge=1, le=20)


class MoveOut(BaseModel):
    ply: int
    move_number: int
    side: str
    san: str
    uci: str
    fen_before: str


class GameSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    white: str | None
    black: str | None
    result: str | None
    user_color: str
    source: str
    review_status: str
    accuracy: float | None
    played_at: datetime | None
    created_at: datetime
    ply_count: int = 0
    outcome: str = "unknown"


class GameDetail(GameSummary):
    pgn: str
    moves: list[MoveOut] = []
    fens: list[str] = []


class ImportResult(BaseModel):
    imported: list[GameSummary]
    skipped: list[str] = []
