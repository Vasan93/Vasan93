"""The progress dashboard."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models import User
from app.schemas.dashboard import DashboardOut, WeaknessProgressOut
from app.services import dashboard as service

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> DashboardOut:
    data = service.build(db, user)
    return DashboardOut(
        rating=data.rating,
        rating_history=[asdict(point) for point in data.rating_history],  # type: ignore[arg-type]
        rating_change_30d=data.rating_change_30d,
        streak_days=data.streak_days,
        best_streak=data.best_streak,
        puzzles_attempted=data.puzzles_attempted,
        puzzles_solved=data.puzzles_solved,
        lessons_completed=data.lessons_completed,
        games_reviewed=data.games_reviewed,
        average_accuracy=data.average_accuracy,
        weaknesses=[
            WeaknessProgressOut(**{**asdict(item), "accuracy": round(item.accuracy, 3)})
            for item in data.weaknesses
        ],
        activity=[asdict(day) for day in data.activity],  # type: ignore[arg-type]
        status_counts=data.status_counts,
    )
