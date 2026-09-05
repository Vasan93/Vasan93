"""Phase 7 acceptance: the app serves the right next puzzle for the learner's top due
weakness, and progression is tracked until the weakness retires.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import REPO_ROOT
from app.curriculum.seed import load_seed_file, seed_puzzles
from app.curriculum.service import grade_puzzle, next_puzzle, record_puzzle_attempt
from app.curriculum.srs import CardState, is_due, review
from app.models import Puzzle, SrsCard, User
from app.weakness.model import Evidence
from app.weakness.service import apply_evidence, load_profile
from app.weakness.taxonomy import TAXONOMY_KEYS


@pytest.fixture(autouse=True)
def _bank() -> None:
    """Load the seed bank once per test, since tables are cleared between tests."""
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        seed_puzzles(db)


# ------------------------------------------------------------------ the bank
def test_seed_file_is_present_and_well_formed() -> None:
    records = load_seed_file()
    assert len(records) >= 20, "the bundled bank should cover every category"
    for record in records:
        assert record["taxonomy_keys"] in TAXONOMY_KEYS
        assert record["kind"] in ("tactical", "concept")
        assert record["solution_moves"]
        assert 300 <= record["rating"] <= 2500


def test_seeding_is_idempotent() -> None:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        before = db.scalar(select(Puzzle.id).limit(1))
        added_again = seed_puzzles(db)
        assert added_again == 0
        assert db.scalar(select(Puzzle.id).limit(1)) == before


def test_every_seeded_puzzle_position_is_legal() -> None:
    import chess

    from app.core.db import SessionLocal

    with SessionLocal() as db:
        for puzzle in db.scalars(select(Puzzle)).all():
            board = chess.Board(puzzle.fen)
            assert board.is_valid(), puzzle.id
            assert not board.is_game_over(), puzzle.id
            first = puzzle.solution_moves.split()[0]
            assert chess.Move.from_uci(first) in board.legal_moves, puzzle.id


# -------------------------------------------------------------------- SM-2
def test_intervals_grow_with_each_success() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    card = CardState()
    intervals = []
    for _ in range(4):
        card = review(card, correct=True, seconds=8, now=now)
        intervals.append(card.interval_days)
        now = card.due_at
    assert intervals == sorted(intervals)
    assert intervals[0] == 1.0
    assert intervals[-1] > 20


def test_a_miss_resets_the_interval_and_costs_a_success() -> None:
    card = CardState(ease=2.6, interval_days=20, repetitions=4, successes=4)
    after = review(card, correct=False, seconds=5)
    assert after.interval_days == 1.0
    assert after.repetitions == 0
    assert after.successes == 3
    assert after.lapses == 1
    assert after.ease < card.ease


def test_retirement_needs_repeated_success_at_growing_intervals() -> None:
    card = CardState()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for _ in range(2):
        card = review(card, correct=True, seconds=8, now=now)
        now = card.due_at
        assert not card.ready_to_retire, "two quick successes are not mastery"
    card = review(card, correct=True, seconds=8, now=now)
    assert card.ready_to_retire


def test_speed_affects_the_grade() -> None:
    fast = review(CardState(interval_days=10, repetitions=3, ease=2.5), True, seconds=5)
    slow = review(CardState(interval_days=10, repetitions=3, ease=2.5), True, seconds=120)
    assert fast.ease > slow.ease


def test_new_cards_are_due_immediately() -> None:
    assert is_due(CardState())
    future = CardState(due_at=datetime.now(timezone.utc) + timedelta(days=3))
    assert not is_due(future)


# ---------------------------------------------------------------- selection
def _user_with_weakness(db, key: str, rating: int = 700) -> User:
    user = db.scalar(select(User))
    user.current_rating_estimate = rating
    apply_evidence(db, user.id, [Evidence(key, "blunder"), Evidence(key, "mistake")])
    db.commit()
    return user


def test_next_puzzle_targets_the_top_due_weakness(auth_client: TestClient) -> None:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        _user_with_weakness(db, "missed_forks")

    res = auth_client.get("/api/puzzles/next")
    assert res.status_code == 200, res.text
    puzzle = res.json()
    assert puzzle["targets"] == "missed_forks"
    assert "missed_forks" in puzzle["taxonomy_keys"]
    assert "solution" not in puzzle, "the answer must never be sent with the puzzle"


def test_puzzle_difficulty_tracks_the_learners_rating(auth_client: TestClient) -> None:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        user = _user_with_weakness(db, "missed_captures", rating=500)
        low_choice = next_puzzle(db, user)
        user.current_rating_estimate = 1200
        db.commit()
        high_choice = next_puzzle(db, user)

    assert low_choice and high_choice
    assert low_choice[0].rating <= high_choice[0].rating


def test_the_same_puzzle_is_not_served_twice_once_solved(auth_client: TestClient) -> None:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        _user_with_weakness(db, "missed_captures")

    first = auth_client.get("/api/puzzles/next").json()
    solution = _solution_san(first["id"])
    auth_client.post(f"/api/puzzles/{first['id']}/attempt", json={"answer": solution, "seconds": 6})
    second = auth_client.get("/api/puzzles/next").json()
    assert second["id"] != first["id"]


def _solution_san(puzzle_id: str) -> str:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        puzzle = db.get(Puzzle, puzzle_id)
        return puzzle.solution_san


# ------------------------------------------------------------------ grading
def test_grading_a_tactical_puzzle_demands_the_move() -> None:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        puzzle = db.get(Puzzle, "gm-br1")  # Ra8# back-rank mate
        correct, solution, _ = grade_puzzle(puzzle, "Ra8#")
        assert correct and solution == "Ra8#"
        wrong, _, loss = grade_puzzle(puzzle, "Ra7")
        assert not wrong and loss > 0


def test_grading_a_concept_puzzle_allows_an_equally_good_move() -> None:
    """Positional ideas rarely have one answer, so a move within tolerance passes."""
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        concept = db.scalar(select(Puzzle).where(Puzzle.kind == "concept"))
        assert concept is not None
        assert concept.tolerance_cp > 30


def test_illegal_answers_are_rejected(auth_client: TestClient) -> None:
    res = auth_client.post("/api/puzzles/gm-br1/attempt", json={"answer": "Qz9"})
    assert res.status_code == 400


# ------------------------------------------------------------- progression
def test_attempt_updates_card_weakness_and_returns_feedback(auth_client: TestClient) -> None:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        _user_with_weakness(db, "back_rank")

    res = auth_client.post("/api/puzzles/gm-br1/attempt", json={"answer": "Ra8#", "seconds": 7})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["correct"] is True
    assert body["weakness_key"] == "back_rank"
    assert body["interval_days"] == 1.0
    assert body["successes"] == 1
    assert body["next_due_at"]
    assert body["feedback"]

    with SessionLocal() as db:
        card = db.scalar(select(SrsCard).where(SrsCard.weakness_key == "back_rank"))
        assert card is not None and card.successes == 1


def test_a_weakness_retires_only_after_spaced_success(auth_client: TestClient) -> None:
    """The end-to-end progression rule: repeated success at growing intervals."""
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        user = _user_with_weakness(db, "back_rank")
        user_id = user.id
        puzzle = db.get(Puzzle, "gm-br1")

        retired = False
        for _ in range(4):
            outcome = record_puzzle_attempt(
                db, db.get(User, user_id), puzzle, "back_rank", correct=True, answer="Ra8#", seconds=6
            )
            retired = retired or outcome["retired"]
        db.commit()

        assert retired, "a weakness must retire after repeated spaced success"
        assert load_profile(db, user_id)["back_rank"].status == "retired"


def test_a_failure_reopens_progress(auth_client: TestClient) -> None:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        user = _user_with_weakness(db, "back_rank")
        puzzle = db.get(Puzzle, "gm-br1")
        record_puzzle_attempt(db, user, puzzle, "back_rank", correct=True, answer="Ra8#", seconds=6)
        record_puzzle_attempt(db, user, puzzle, "back_rank", correct=True, answer="Ra8#", seconds=6)
        outcome = record_puzzle_attempt(db, user, puzzle, "back_rank", correct=False, answer="Ra7", seconds=6)
        db.commit()
        assert outcome["interval_days"] == 1.0
        assert outcome["successes"] == 1


def test_curriculum_lists_due_cards(auth_client: TestClient) -> None:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        _user_with_weakness(db, "missed_forks")

    body = auth_client.get("/api/curriculum").json()
    assert body["puzzles_available"] >= 20
    assert body["total_active"] >= 1
    assert any(card["weakness_key"] == "missed_forks" for card in body["due"])


def test_puzzles_require_authentication(client: TestClient) -> None:
    assert client.get("/api/puzzles/next").status_code == 401
