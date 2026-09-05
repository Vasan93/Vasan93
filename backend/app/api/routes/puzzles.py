"""Puzzle training and the spaced-repetition curriculum."""
from __future__ import annotations

import chess
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import RateLimit, get_current_user
from app.coaching import service as coaching
from app.coaching.brain import LearnerContext, get_brain
from app.core.db import get_db
from app.curriculum.service import (
    due_cards,
    grade_puzzle,
    next_puzzle,
    record_puzzle_attempt,
)
from app.models import Puzzle, User
from app.schemas.curriculum import (
    CurriculumOut,
    DueCardOut,
    PuzzleAttemptRequest,
    PuzzleAttemptResult,
    PuzzleOut,
)
from app.weakness.service import load_profile
from app.weakness.taxonomy import label as taxonomy_label

router = APIRouter(tags=["puzzles"])

attempt_limit = RateLimit(limit=300, window_seconds=3600, name="puzzle-attempt")


def _puzzle_out(puzzle: Puzzle, targets: str) -> PuzzleOut:
    board = chess.Board(puzzle.fen)
    return PuzzleOut(
        id=puzzle.id,
        fen=puzzle.fen,
        rating=puzzle.rating,
        kind=puzzle.kind,
        themes=puzzle.themes.split(),
        taxonomy_keys=puzzle.taxonomy_keys.split(),
        targets=targets,
        targets_label=taxonomy_label(targets),
        side_to_move="white" if board.turn == chess.WHITE else "black",
        source=puzzle.source,
    )


@router.get("/puzzles/next", response_model=PuzzleOut)
def get_next_puzzle(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> PuzzleOut:
    chosen = next_puzzle(db, user)
    db.commit()
    if chosen is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No puzzles left in the bank. Import more with scripts/import_lichess_puzzles.py.",
        )
    puzzle, targets = chosen
    return _puzzle_out(puzzle, targets)


@router.post("/puzzles/{puzzle_id}/attempt", response_model=PuzzleAttemptResult)
def attempt_puzzle(
    puzzle_id: str,
    payload: PuzzleAttemptRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _limit: None = Depends(attempt_limit),
) -> PuzzleAttemptResult:
    puzzle = db.get(Puzzle, puzzle_id)
    if puzzle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Puzzle not found.")

    try:
        correct, solution, cp_loss = grade_puzzle(puzzle, payload.answer)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    keys = puzzle.taxonomy_keys.split()
    targets = payload.targets if payload.targets in keys else keys[0]

    outcome = record_puzzle_attempt(
        db, user, puzzle, targets, correct=correct, answer=payload.answer, seconds=payload.seconds
    )

    learner = coaching.learner_context(db, user)
    facts = {
        "fen": puzzle.fen,
        "question": "Find the best move.",
        "answer": solution,
        "student_answer": payload.answer,
        "correct": correct,
        "engine_note": "" if correct else f"Their move loses {cp_loss} centipawns.",
    }
    try:
        feedback = get_brain().check_feedback(learner, facts)
    except Exception:
        from app.coaching.brain import TemplateBrain

        feedback = TemplateBrain().check_feedback(learner, facts)
    coaching.log_exchange(db, user, "check", feedback)
    db.commit()

    return PuzzleAttemptResult(
        correct=correct,
        solution=solution,
        cp_loss=cp_loss,
        weakness_key=targets,
        weakness_label=taxonomy_label(targets),
        confidence=outcome["confidence"],
        interval_days=outcome["interval_days"],
        successes=outcome["successes"],
        next_due_at=outcome["next_due_at"],
        retired=outcome["retired"],
        feedback=feedback.text,
        feedback_source=feedback.source,
    )


@router.get("/curriculum", response_model=CurriculumOut)
def get_curriculum(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> CurriculumOut:
    due = due_cards(db, user)
    profile = load_profile(db, user.id)
    total = db.scalar(select(func.count()).select_from(Puzzle)) or 0
    db.commit()
    return CurriculumOut(
        due=[DueCardOut(**card.__dict__) for card in due],
        total_active=sum(1 for score in profile.values() if score.status != "retired"),
        puzzles_available=total,
    )
