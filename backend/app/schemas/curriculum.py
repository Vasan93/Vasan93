"""Puzzle and curriculum payloads."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PuzzleOut(BaseModel):
    """A puzzle as the learner sees it. The solution is never included."""

    id: str
    fen: str
    rating: int
    kind: str
    themes: list[str]
    taxonomy_keys: list[str]
    targets: str  # the weakness this attempt is training
    targets_label: str
    side_to_move: str
    source: str


class PuzzleAttemptRequest(BaseModel):
    answer: str = Field(max_length=12)
    seconds: float | None = Field(default=None, ge=0, le=3600)
    targets: str | None = Field(default=None, max_length=48)


class PuzzleAttemptResult(BaseModel):
    correct: bool
    solution: str
    cp_loss: int
    weakness_key: str
    weakness_label: str
    confidence: float
    interval_days: float
    successes: int
    next_due_at: datetime | None
    retired: bool
    feedback: str
    feedback_source: str


class DueCardOut(BaseModel):
    weakness_key: str
    label: str
    confidence: float
    due_at: datetime | None
    interval_days: float
    successes: int
    status: str


class CurriculumOut(BaseModel):
    due: list[DueCardOut]
    total_active: int
    puzzles_available: int
