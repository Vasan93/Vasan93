"""Dashboard payloads."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class RatingPointOut(BaseModel):
    rating: int
    source: str
    recorded_at: datetime


class DailyActivityOut(BaseModel):
    day: date
    puzzles: int
    correct: int


class WeaknessProgressOut(BaseModel):
    taxonomy_key: str
    label: str
    category: str
    status: str
    confidence: float
    evidence_count: int
    success_count: int
    attempts: int
    solved: int
    accuracy: float


class DashboardOut(BaseModel):
    rating: int
    rating_history: list[RatingPointOut]
    rating_change_30d: int
    streak_days: int
    best_streak: int
    puzzles_attempted: int
    puzzles_solved: int
    lessons_completed: int
    games_reviewed: int
    average_accuracy: float | None
    weaknesses: list[WeaknessProgressOut]
    activity: list[DailyActivityOut]
    status_counts: dict[str, int]
