"""Practice game payloads."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NewGameRequest(BaseModel):
    color: Literal["white", "black", "random"] = "white"


class MoveRequest(BaseModel):
    move: str = Field(max_length=12)


class PracticeStateOut(BaseModel):
    game_id: int
    fen: str
    user_color: str
    turn: str
    move_history: list[str]
    last_move_uci: str | None
    is_over: bool
    result: str | None
    outcome_text: str
    opponent_kind: str
    opponent_rating: int
    opponent_note: str
    in_check: bool
    legal_move_count: int
    review_status: str = "pending"
