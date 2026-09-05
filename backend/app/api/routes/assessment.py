"""The skill assessment: where a new learner starts."""
from __future__ import annotations

import chess
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import RateLimit, get_current_user
from app.assessment import service
from app.assessment.rating import ASSESSMENT_LENGTH
from app.core.db import get_db
from app.models import Puzzle, User
from app.schemas.assessment import (
    AssessmentAnswer,
    AssessmentAnswerResult,
    AssessmentResult,
    AssessmentStatus,
)
from app.schemas.coaching import CoachingText
from app.schemas.curriculum import PuzzleOut
from app.schemas.weakness import WeaknessOut
from app.weakness.service import load_profile
from app.weakness.taxonomy import label as taxonomy_label

router = APIRouter(prefix="/assessment", tags=["assessment"])

assessment_limit = RateLimit(limit=200, window_seconds=3600, name="assessment")


def _puzzle_out(puzzle: Puzzle) -> PuzzleOut:
    board = chess.Board(puzzle.fen)
    key = puzzle.taxonomy_keys.split()[0]
    return PuzzleOut(
        id=puzzle.id,
        fen=puzzle.fen,
        rating=puzzle.rating,
        kind=puzzle.kind,
        themes=puzzle.themes.split(),
        taxonomy_keys=puzzle.taxonomy_keys.split(),
        targets=key,
        targets_label=taxonomy_label(key),
        side_to_move="white" if board.turn == chess.WHITE else "black",
        source=puzzle.source,
    )


def _status(state: service.AssessmentState) -> AssessmentStatus:
    return AssessmentStatus(
        answered=state.answered,
        total=state.total,
        finished=state.finished,
        rating_so_far=state.estimate.rating,
        next_puzzle=_puzzle_out(state.next_puzzle) if state.next_puzzle else None,
    )


@router.get("", response_model=AssessmentStatus)
def get_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AssessmentStatus:
    state = service.state(db, user)
    db.commit()
    return _status(state)


@router.post("/restart", response_model=AssessmentStatus)
def restart(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AssessmentStatus:
    service.restart(db, user)
    state = service.state(db, user)
    db.commit()
    return _status(state)


@router.post("/answer", response_model=AssessmentAnswerResult)
def answer(
    payload: AssessmentAnswer,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _limit: None = Depends(assessment_limit),
) -> AssessmentAnswerResult:
    try:
        outcome = service.answer(db, user, payload.puzzle_id, payload.answer, payload.seconds)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    return AssessmentAnswerResult(
        correct=outcome["correct"], solution=outcome["solution"], status=_status(outcome["state"])
    )


@router.post("/finish", response_model=AssessmentResult)
def finish(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _limit: None = Depends(assessment_limit),
) -> AssessmentResult:
    try:
        result = service.finish(db, user)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    profile = load_profile(db, user.id)
    db.commit()

    summary = result["summary"]
    return AssessmentResult(
        rating=result["rating"],
        confidence_interval=result["confidence_interval"],
        answered=result["answered"],
        correct=result["correct"],
        area_summary=result["area_summary"],
        top_weaknesses=[
            WeaknessOut.from_score(profile[key]) for key in result["top_weaknesses"] if key in profile
        ],
        summary=CoachingText(
            text=summary.text,
            source=summary.source,
            language=summary.language,
            requested_language=summary.requested_language,
            language_fallback=summary.language_fallback,
            notes=summary.notes,
        ),
    )


@router.get("/length")
def assessment_length() -> dict[str, int]:
    return {"length": ASSESSMENT_LENGTH}
