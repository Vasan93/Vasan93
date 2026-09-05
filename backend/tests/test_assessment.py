"""Phase 6 acceptance: a new user completes the assessment and lands on a personalised
starting point -- a rating estimate, their top weaknesses, and a summary from the coach.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.assessment.rating import (
    ASSESSMENT_LENGTH,
    START_RATING,
    estimate_from,
    expected_score,
    k_factor,
    next_difficulty,
    update,
)
from app.curriculum.seed import seed_puzzles
from app.models import Puzzle, RatingHistory, User


@pytest.fixture(autouse=True)
def _bank() -> None:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        seed_puzzles(db)


# --------------------------------------------------------------- estimation
def test_expected_score_is_symmetric() -> None:
    assert expected_score(1000, 1000) == pytest.approx(0.5)
    assert expected_score(1400, 1000) + expected_score(1000, 1400) == pytest.approx(1.0)


def test_k_factor_falls_as_evidence_accumulates() -> None:
    assert k_factor(0) > k_factor(5) > k_factor(10) > k_factor(50)


def test_solving_raises_and_missing_lowers_the_estimate() -> None:
    assert update(1000, 1000, correct=True, attempts=0) > 1000
    assert update(1000, 1000, correct=False, attempts=0) < 1000


def test_an_easy_solve_moves_the_estimate_less_than_a_hard_one() -> None:
    easy = update(1200, 600, correct=True, attempts=0) - 1200
    hard = update(1200, 1800, correct=True, attempts=0) - 1200
    assert hard > easy


def test_estimate_converges_between_solved_and_missed_difficulty() -> None:
    results = [(600, True), (800, True), (1000, True), (1200, False), (1000, True),
               (1150, False), (1050, True), (1150, False), (1050, True), (1100, False)]
    estimate = estimate_from(results)
    assert 900 < estimate.rating < 1300
    assert estimate.answered == 10
    assert estimate.correct == 6
    assert estimate.confidence_interval < 200


def test_estimate_separates_strong_and_weak_players() -> None:
    strong = estimate_from([(rating, True) for rating in range(600, 2600, 200)])
    weak = estimate_from([(rating, False) for rating in (1000, 800, 700, 600, 500, 500, 500, 500, 500, 500)])
    assert strong.rating > 1400
    assert weak.rating < 700


def test_confidence_interval_narrows_with_more_answers() -> None:
    few = estimate_from([(1000, True)])
    many = estimate_from([(1000, True)] * 16)
    assert few.confidence_interval > many.confidence_interval


def test_difficulty_adapts_to_the_last_answer() -> None:
    assert next_difficulty(1000, 1, last_correct=True) > 1000
    assert next_difficulty(1000, 1, last_correct=False) < 1000
    assert next_difficulty(1000, 0, last_correct=None) == 1000
    # Steps shrink as the estimate settles.
    early = next_difficulty(1000, 1, True) - 1000
    late = next_difficulty(1000, 8, True) - 1000
    assert early > late


# ---------------------------------------------------------------- the flow
def _solution(puzzle_id: str) -> str:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        return db.get(Puzzle, puzzle_id).solution_san


def _wrong_move(fen: str) -> str:
    import chess

    board = chess.Board(fen)
    from app.core.db import SessionLocal  # noqa: F401

    best = None
    for move in board.legal_moves:
        san = board.san(move)
        if best is None:
            best = san
    return best or "e4"


def test_assessment_starts_with_a_puzzle_and_a_default_rating(auth_client: TestClient) -> None:
    body = auth_client.get("/api/assessment").json()
    assert body["answered"] == 0
    assert body["total"] == ASSESSMENT_LENGTH
    assert body["finished"] is False
    assert body["rating_so_far"] == START_RATING
    assert body["next_puzzle"] is not None
    assert "solution" not in body["next_puzzle"]


def test_assessment_covers_more_than_one_area(auth_client: TestClient) -> None:
    seen: set[str] = set()
    for _ in range(4):
        status = auth_client.get("/api/assessment").json()
        puzzle = status["next_puzzle"]
        if puzzle is None:
            break
        seen.update(puzzle["taxonomy_keys"])
        auth_client.post(
            "/api/assessment/answer",
            json={"puzzle_id": puzzle["id"], "answer": _solution(puzzle["id"]), "seconds": 8},
        )
    assert len(seen) >= 3, "the assessment must sample several areas, not just tactics"


def test_a_full_assessment_produces_a_personalised_starting_point(auth_client: TestClient) -> None:
    """The acceptance criterion for this phase."""
    answered = 0
    while answered < ASSESSMENT_LENGTH:
        status = auth_client.get("/api/assessment").json()
        if status["finished"] or status["next_puzzle"] is None:
            break
        puzzle = status["next_puzzle"]
        # Solve the easy half, miss the hard half, so the estimate has to land in between.
        move = _solution(puzzle["id"]) if puzzle["rating"] <= 800 else _wrong_move(puzzle["fen"])
        res = auth_client.post(
            "/api/assessment/answer",
            json={"puzzle_id": puzzle["id"], "answer": move, "seconds": 12},
        )
        assert res.status_code == 200, res.text
        answered += 1

    result = auth_client.post("/api/assessment/finish")
    assert result.status_code == 200, result.text
    body = result.json()

    assert 400 <= body["rating"] <= 2800
    assert body["answered"] == answered
    assert body["area_summary"]
    assert body["summary"]["text"], "the coach must say something about where they stand"
    assert body["top_weaknesses"], "failures must seed a weakness profile"
    assert all(weakness["confidence"] > 0 for weakness in body["top_weaknesses"])

    profile = auth_client.get("/api/auth/me").json()
    assert profile["assessment_completed"] is True
    assert profile["current_rating_estimate"] == body["rating"]

    from app.core.db import SessionLocal

    with SessionLocal() as db:
        history = db.scalars(select(RatingHistory).where(RatingHistory.source == "assessment")).all()
    assert history, "the starting rating must appear on the trajectory"


def test_answering_the_same_puzzle_twice_is_rejected(auth_client: TestClient) -> None:
    puzzle = auth_client.get("/api/assessment").json()["next_puzzle"]
    payload = {"puzzle_id": puzzle["id"], "answer": _solution(puzzle["id"]), "seconds": 5}
    assert auth_client.post("/api/assessment/answer", json=payload).status_code == 200
    assert auth_client.post("/api/assessment/answer", json=payload).status_code == 400


def test_finishing_without_answering_is_rejected(auth_client: TestClient) -> None:
    assert auth_client.post("/api/assessment/finish").status_code == 400


def test_restart_clears_a_previous_run(auth_client: TestClient) -> None:
    puzzle = auth_client.get("/api/assessment").json()["next_puzzle"]
    auth_client.post(
        "/api/assessment/answer",
        json={"puzzle_id": puzzle["id"], "answer": _solution(puzzle["id"]), "seconds": 5},
    )
    assert auth_client.get("/api/assessment").json()["answered"] == 1

    restarted = auth_client.post("/api/assessment/restart").json()
    assert restarted["answered"] == 0
    assert auth_client.get("/api/auth/me").json()["assessment_completed"] is False


def test_assessment_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/assessment").status_code == 401
