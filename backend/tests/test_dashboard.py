"""Phase 9 acceptance: the dashboard reflects real user history accurately."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.curriculum.seed import seed_puzzles
from app.services.dashboard import compute_streaks


@pytest.fixture(autouse=True)
def _bank() -> None:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        seed_puzzles(db)


# ---------------------------------------------------------------- streaks
def test_no_activity_means_no_streak() -> None:
    assert compute_streaks(set()) == (0, 0)


def test_consecutive_days_count_as_one_streak() -> None:
    today = date(2026, 3, 10)
    days = {today, today - timedelta(days=1), today - timedelta(days=2)}
    current, best = compute_streaks(days, today=today)
    assert current == 3
    assert best == 3


def test_a_gap_breaks_the_current_streak_but_not_the_best() -> None:
    today = date(2026, 3, 10)
    days = {
        date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4),  # a four-day run
        today,
    }
    current, best = compute_streaks(days, today=today)
    assert current == 1
    assert best == 4


def test_yesterday_still_counts_as_an_unbroken_streak() -> None:
    """A streak should not die the moment midnight passes."""
    today = date(2026, 3, 10)
    days = {today - timedelta(days=1), today - timedelta(days=2)}
    current, _ = compute_streaks(days, today=today)
    assert current == 2


def test_an_old_run_does_not_count_as_current() -> None:
    today = date(2026, 3, 10)
    days = {date(2026, 2, 1), date(2026, 2, 2)}
    current, best = compute_streaks(days, today=today)
    assert current == 0
    assert best == 2


# -------------------------------------------------------------- the API
def test_dashboard_starts_empty_but_valid(auth_client: TestClient) -> None:
    body = auth_client.get("/api/dashboard").json()
    assert body["rating"] == 1000
    assert body["puzzles_attempted"] == 0
    assert body["streak_days"] == 0
    assert body["average_accuracy"] is None
    assert body["weaknesses"] == []
    # Signup records the first point on the trajectory.
    assert len(body["rating_history"]) == 1


def test_dashboard_counts_real_activity(auth_client: TestClient) -> None:
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models import Puzzle, User
    from app.weakness.model import Evidence
    from app.weakness.service import apply_evidence

    with SessionLocal() as db:
        user = db.scalar(select(User))
        apply_evidence(db, user.id, [Evidence("back_rank", "blunder")])
        db.commit()

    solved = auth_client.post("/api/puzzles/gm-br1/attempt", json={"answer": "Ra8#", "seconds": 6})
    assert solved.status_code == 200
    missed = auth_client.post("/api/puzzles/gm-br2/attempt", json={"answer": "Rd2", "seconds": 20})
    assert missed.status_code == 200

    body = auth_client.get("/api/dashboard").json()
    assert body["puzzles_attempted"] == 2
    assert body["puzzles_solved"] == 1
    assert body["streak_days"] == 1
    assert len(body["activity"]) == 1
    assert body["activity"][0]["puzzles"] == 2
    assert body["activity"][0]["correct"] == 1

    back_rank = next(item for item in body["weaknesses"] if item["taxonomy_key"] == "back_rank")
    assert back_rank["attempts"] == 2
    assert back_rank["solved"] == 1
    assert back_rank["accuracy"] == pytest.approx(0.5)


def test_dashboard_reports_rating_change_and_history(auth_client: TestClient) -> None:
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models import RatingHistory, User

    with SessionLocal() as db:
        user = db.scalar(select(User))
        db.add(RatingHistory(user_id=user.id, rating=1150, source="puzzles"))
        user.current_rating_estimate = 1150
        db.commit()

    body = auth_client.get("/api/dashboard").json()
    assert body["rating"] == 1150
    assert len(body["rating_history"]) == 2
    assert body["rating_change_30d"] == 150
    assert [point["rating"] for point in body["rating_history"]] == [1000, 1150]


@pytest.mark.slow
def test_dashboard_reflects_a_reviewed_game(auth_client: TestClient) -> None:
    pgn = """[Event "Club night"]
[White "meena"]
[Black "rival"]
[Result "0-1"]

1. e4 e5 2. Qh5 Nc6 3. Bc4 g6 4. Qf3 Nf6 5. Qb3 Nd4 6. Qc3 Bc5 7. Nf3 Nxf3+ 0-1"""
    game_id = auth_client.post("/api/games/import/pgn", json={"pgn": pgn, "user_color": "white"}).json()[
        "imported"
    ][0]["id"]
    auth_client.post(f"/api/games/{game_id}/review")

    from app.services.jobs import get_job_runner

    assert get_job_runner().wait_for(f"review:{game_id}", timeout=300)["state"] == "done"

    body = auth_client.get("/api/dashboard").json()
    assert body["games_reviewed"] == 1
    assert body["average_accuracy"] is not None
    assert 0 < body["average_accuracy"] <= 100
    assert body["weaknesses"], "a reviewed game must show up as weakness progress"
    assert body["status_counts"]["active"] >= 1


def test_dashboard_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/dashboard").status_code == 401
