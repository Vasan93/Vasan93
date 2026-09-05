"""The skill assessment.

A short adaptive run of calibrated puzzles, balanced across the five areas of the
taxonomy, that produces a starting rating and a first weakness profile. Real games, when
the learner has imported any, are worth far more than puzzles, so they feed the same
profile.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessment.rating import (
    ASSESSMENT_LENGTH,
    START_RATING,
    Estimate,
    estimate_from,
    next_difficulty,
)
from app.coaching import service as coaching
from app.core.logging import get_logger
from app.curriculum.service import grade_puzzle
from app.models import Game, Puzzle, PuzzleAttempt, RatingHistory, User
from app.weakness.model import Evidence, top_weaknesses
from app.weakness.service import apply_evidence, load_profile
from app.weakness.taxonomy import TAXONOMY, Category

log = get_logger(__name__)

CONTEXT = "assessment"

# Areas the assessment must sample, in the order it first reaches for them.
AREA_ORDER: tuple[Category, ...] = (
    Category.TACTICAL,
    Category.ENDGAME,
    Category.OPENING,
    Category.POSITIONAL,
    Category.TACTICAL,
)


@dataclass
class AssessmentState:
    answered: int
    total: int
    estimate: Estimate
    finished: bool
    next_puzzle: Puzzle | None = None
    last_correct: bool | None = None


def _attempts(db: Session, user: User) -> list[PuzzleAttempt]:
    return list(
        db.scalars(
            select(PuzzleAttempt)
            .where(PuzzleAttempt.user_id == user.id, PuzzleAttempt.context == CONTEXT)
            .order_by(PuzzleAttempt.id)
        ).all()
    )


def _results(db: Session, attempts: list[PuzzleAttempt]) -> list[tuple[int, bool]]:
    ratings = {
        puzzle.id: puzzle.rating
        for puzzle in db.scalars(
            select(Puzzle).where(Puzzle.id.in_([attempt.puzzle_id for attempt in attempts] or [""]))
        ).all()
    }
    return [(ratings.get(attempt.puzzle_id, START_RATING), attempt.correct) for attempt in attempts]


def _category_of(puzzle: Puzzle) -> Category | None:
    for key in puzzle.taxonomy_keys.split():
        entry = TAXONOMY.get(key)
        if entry:
            return entry.category
    return None


def _select_puzzle(db: Session, answered: int, target: int, used: set[str]) -> Puzzle | None:
    """Pick the next puzzle: right area if possible, closest to the target difficulty."""
    candidates = [puzzle for puzzle in db.scalars(select(Puzzle)).all() if puzzle.id not in used]
    if not candidates:
        return None

    wanted = AREA_ORDER[answered % len(AREA_ORDER)]
    in_area = [puzzle for puzzle in candidates if _category_of(puzzle) is wanted]
    pool = in_area or candidates
    pool.sort(key=lambda puzzle: abs(puzzle.rating - target))
    return pool[0]


def state(db: Session, user: User) -> AssessmentState:
    attempts = _attempts(db, user)
    results = _results(db, attempts)
    estimate = estimate_from(results, start=START_RATING)
    last_correct = attempts[-1].correct if attempts else None
    answered = len(attempts)

    if answered >= ASSESSMENT_LENGTH:
        return AssessmentState(answered=answered, total=ASSESSMENT_LENGTH, estimate=estimate, finished=True)

    target = next_difficulty(estimate.rating if answered else START_RATING, answered, last_correct)
    used = {attempt.puzzle_id for attempt in attempts}
    puzzle = _select_puzzle(db, answered, target, used)

    return AssessmentState(
        answered=answered,
        total=ASSESSMENT_LENGTH,
        estimate=estimate,
        finished=puzzle is None,
        next_puzzle=puzzle,
        last_correct=last_correct,
    )


def restart(db: Session, user: User) -> None:
    """Clear a previous assessment so it can be taken again."""
    for attempt in _attempts(db, user):
        db.delete(attempt)
    user.assessment_completed = False
    db.flush()


def answer(db: Session, user: User, puzzle_id: str, response: str, seconds: float | None) -> dict:
    """Grade one assessment answer and advance the run."""
    puzzle = db.get(Puzzle, puzzle_id)
    if puzzle is None:
        raise ValueError("Puzzle not found.")

    attempts = _attempts(db, user)
    if len(attempts) >= ASSESSMENT_LENGTH:
        raise ValueError("The assessment is already complete.")
    if any(attempt.puzzle_id == puzzle_id for attempt in attempts):
        raise ValueError("That puzzle has already been answered.")

    correct, solution, cp_loss = grade_puzzle(puzzle, response)
    db.add(
        PuzzleAttempt(
            user_id=user.id,
            puzzle_id=puzzle.id,
            weakness_key=puzzle.taxonomy_keys.split()[0],
            context=CONTEXT,
            correct=correct,
            played_move=response[:12],
            time_ms=int(seconds * 1000) if seconds is not None else None,
        )
    )
    db.flush()

    return {"correct": correct, "solution": solution, "cp_loss": cp_loss, "state": state(db, user)}


def _seed_weaknesses(db: Session, user: User, attempts: list[PuzzleAttempt]) -> None:
    """Failed assessment puzzles are evidence, the same as mistakes in a real game."""
    puzzles = {
        puzzle.id: puzzle
        for puzzle in db.scalars(
            select(Puzzle).where(Puzzle.id.in_([attempt.puzzle_id for attempt in attempts] or [""]))
        ).all()
    }
    evidence: list[Evidence] = []
    for attempt in attempts:
        if attempt.correct:
            continue
        puzzle = puzzles.get(attempt.puzzle_id)
        if puzzle is None:
            continue
        for key in puzzle.taxonomy_keys.split():
            evidence.append(Evidence(taxonomy_key=key, label="mistake"))
    if evidence:
        apply_evidence(db, user.id, evidence)


def _area_summary(db: Session, attempts: list[PuzzleAttempt]) -> str:
    puzzles = {
        puzzle.id: puzzle
        for puzzle in db.scalars(
            select(Puzzle).where(Puzzle.id.in_([attempt.puzzle_id for attempt in attempts] or [""]))
        ).all()
    }
    tally: dict[str, list[int]] = {}
    for attempt in attempts:
        puzzle = puzzles.get(attempt.puzzle_id)
        category = _category_of(puzzle) if puzzle else None
        if category is None:
            continue
        got, total = tally.setdefault(str(category), [0, 0])
        tally[str(category)] = [got + int(attempt.correct), total + 1]
    return ", ".join(f"{area}: {got} of {total}" for area, (got, total) in sorted(tally.items())) or "no data"


def finish(db: Session, user: User) -> dict:
    """Close the assessment: set the rating, seed weaknesses, write the coach's summary."""
    attempts = _attempts(db, user)
    if not attempts:
        raise ValueError("Nothing has been answered yet.")

    estimate = estimate_from(_results(db, attempts), start=START_RATING)
    _seed_weaknesses(db, user, attempts)

    user.current_rating_estimate = estimate.rating
    user.assessment_completed = True
    db.add(RatingHistory(user_id=user.id, rating=estimate.rating, source=CONTEXT))
    db.flush()

    profile = load_profile(db, user.id)
    top = top_weaknesses(profile, limit=3, include_improving=True)
    games_reviewed = db.scalar(
        select(Game).where(Game.user_id == user.id, Game.review_status == "done").limit(1)
    )

    summary = coaching.summarise_assessment(
        db,
        user,
        {
            "rating": estimate.rating,
            "area_summary": _area_summary(db, attempts),
            "games_reviewed": 1 if games_reviewed else 0,
        },
    )

    return {
        "rating": estimate.rating,
        "confidence_interval": estimate.confidence_interval,
        "answered": estimate.answered,
        "correct": estimate.correct,
        "area_summary": _area_summary(db, attempts),
        "top_weaknesses": [key.taxonomy_key for key in top],
        "summary": summary,
    }
