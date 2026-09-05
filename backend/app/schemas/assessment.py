"""Assessment payloads."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.coaching import CoachingText
from app.schemas.curriculum import PuzzleOut
from app.schemas.weakness import WeaknessOut


class AssessmentStatus(BaseModel):
    answered: int
    total: int
    finished: bool
    rating_so_far: int
    next_puzzle: PuzzleOut | None = None


class AssessmentAnswer(BaseModel):
    puzzle_id: str = Field(max_length=32)
    answer: str = Field(max_length=12)
    seconds: float | None = Field(default=None, ge=0, le=3600)


class AssessmentAnswerResult(BaseModel):
    correct: bool
    solution: str
    status: AssessmentStatus


class AssessmentResult(BaseModel):
    rating: int
    confidence_interval: int
    answered: int
    correct: int
    area_summary: str
    top_weaknesses: list[WeaknessOut]
    summary: CoachingText
