"""Dashboard aggregation.

A beginner's rating moves slowly and noisily, so a rating chart alone is discouraging.
Weakness-level progress moves faster and is the honest signal that the work is paying off,
so both are surfaced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Game, Lesson, PuzzleAttempt, RatingHistory, User
from app.weakness.service import load_profile
from app.weakness.taxonomy import TAXONOMY, label as taxonomy_label

RECENT_DAYS = 30


@dataclass
class RatingPoint:
    rating: int
    source: str
    recorded_at: datetime


@dataclass
class DailyActivity:
    day: date
    puzzles: int
    correct: int


@dataclass
class WeaknessProgress:
    taxonomy_key: str
    label: str
    category: str
    status: str
    confidence: float
    evidence_count: int
    success_count: int
    attempts: int
    solved: int

    @property
    def accuracy(self) -> float:
        return self.solved / self.attempts if self.attempts else 0.0


@dataclass
class Dashboard:
    rating: int
    rating_history: list[RatingPoint]
    rating_change_30d: int
    streak_days: int
    best_streak: int
    puzzles_attempted: int
    puzzles_solved: int
    lessons_completed: int
    games_reviewed: int
    average_accuracy: float | None
    weaknesses: list[WeaknessProgress] = field(default_factory=list)
    activity: list[DailyActivity] = field(default_factory=list)
    status_counts: dict[str, int] = field(default_factory=dict)


def _as_date(value: datetime) -> date:
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).date()


def compute_streaks(days: set[date], today: date | None = None) -> tuple[int, int]:
    """Current and best run of consecutive active days."""
    if not days:
        return 0, 0
    ordered = sorted(days)

    best = run = 1
    for previous, current in zip(ordered, ordered[1:]):
        run = run + 1 if current - previous == timedelta(days=1) else 1
        best = max(best, run)

    today = today or datetime.now(timezone.utc).date()
    # A streak survives until the end of the following day, so today or yesterday counts.
    if ordered[-1] not in (today, today - timedelta(days=1)):
        return 0, best

    current_streak = 1
    for previous, following in zip(reversed(ordered), reversed(ordered[:-1])):
        if previous - following == timedelta(days=1):
            current_streak += 1
        else:
            break
    return current_streak, best


def build(db: Session, user: User) -> Dashboard:
    history = list(
        db.scalars(
            select(RatingHistory).where(RatingHistory.user_id == user.id).order_by(RatingHistory.recorded_at)
        ).all()
    )
    points = [RatingPoint(rating=row.rating, source=row.source, recorded_at=row.recorded_at) for row in history]

    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)
    recent = [point for point in points if _as_date(point.recorded_at) >= cutoff.date()]
    rating_change = (recent[-1].rating - recent[0].rating) if len(recent) >= 2 else 0

    attempts = list(
        db.scalars(select(PuzzleAttempt).where(PuzzleAttempt.user_id == user.id)).all()
    )
    days = {_as_date(attempt.attempted_at) for attempt in attempts}
    streak, best_streak = compute_streaks(days)

    by_day: dict[date, DailyActivity] = {}
    for attempt in attempts:
        day = _as_date(attempt.attempted_at)
        entry = by_day.setdefault(day, DailyActivity(day=day, puzzles=0, correct=0))
        entry.puzzles += 1
        entry.correct += int(attempt.correct)

    per_key: dict[str, list[int]] = {}
    for attempt in attempts:
        if not attempt.weakness_key:
            continue
        tally = per_key.setdefault(attempt.weakness_key, [0, 0])
        tally[0] += 1
        tally[1] += int(attempt.correct)

    profile = load_profile(db, user.id)
    weaknesses: list[WeaknessProgress] = []
    status_counts: dict[str, int] = {"active": 0, "improving": 0, "retired": 0}
    for key, score in profile.items():
        entry = TAXONOMY.get(key)
        attempted, solved = per_key.get(key, [0, 0])
        status_counts[score.status] = status_counts.get(score.status, 0) + 1
        weaknesses.append(
            WeaknessProgress(
                taxonomy_key=key,
                label=taxonomy_label(key),
                category=str(entry.category) if entry else "tactical",
                status=score.status,
                confidence=score.confidence,
                evidence_count=score.evidence_count,
                success_count=score.success_count,
                attempts=attempted,
                solved=solved,
            )
        )
    weaknesses.sort(key=lambda item: (item.status != "active", -item.confidence))

    lessons_completed = db.scalar(
        select(func.count()).select_from(Lesson).where(Lesson.user_id == user.id, Lesson.passed.is_(True))
    ) or 0
    reviewed = list(
        db.scalars(
            select(Game).where(Game.user_id == user.id, Game.review_status == "done")
        ).all()
    )
    accuracies = [game.accuracy for game in reviewed if game.accuracy is not None]

    return Dashboard(
        rating=user.current_rating_estimate,
        rating_history=points,
        rating_change_30d=rating_change,
        streak_days=streak,
        best_streak=best_streak,
        puzzles_attempted=len(attempts),
        puzzles_solved=sum(1 for attempt in attempts if attempt.correct),
        lessons_completed=lessons_completed,
        games_reviewed=len(reviewed),
        average_accuracy=round(sum(accuracies) / len(accuracies), 1) if accuracies else None,
        weaknesses=weaknesses,
        activity=[by_day[day] for day in sorted(by_day)],
        status_counts=status_counts,
    )
