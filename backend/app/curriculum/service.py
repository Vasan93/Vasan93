"""Deciding what the learner practises next, and recording how it went.

"What to teach next" is the highest-confidence active weakness whose spaced-repetition
card is due. Puzzles are then drawn near the learner's rating, slightly above for stretch.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import chess
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.coaching.validation import grade_answer
from app.core.logging import get_logger
from app.curriculum.srs import CardState, is_due, review
from app.engines.stockfish import StockfishEngine, get_analysis_engine
from app.models import Puzzle, PuzzleAttempt, SrsCard, User
from app.weakness.model import eligible_to_retire
from app.weakness.service import load_profile, record_attempt_result, save_profile
from app.weakness.taxonomy import TAXONOMY

log = get_logger(__name__)

# Puzzles are drawn from this window around the learner's rating: a little below so they
# succeed often enough to stay motivated, further above so there is something to stretch for.
RATING_BELOW = 150
RATING_ABOVE = 250


@dataclass
class DueCard:
    weakness_key: str
    label: str
    confidence: float
    due_at: datetime | None
    interval_days: float
    successes: int
    status: str


def _card_state(row: SrsCard) -> CardState:
    return CardState(
        ease=row.ease,
        interval_days=row.interval_days,
        repetitions=row.repetitions,
        successes=row.successes,
        lapses=row.lapses,
        due_at=row.due_at,
    )


def ensure_cards(db: Session, user: User) -> dict[str, SrsCard]:
    """Every active weakness gets a card; retired ones do not."""
    profile = load_profile(db, user.id)
    rows = {row.weakness_key: row for row in db.scalars(select(SrsCard).where(SrsCard.user_id == user.id)).all()}

    for key, score in profile.items():
        if score.status == "retired":
            continue
        if key not in rows:
            card = SrsCard(user_id=user.id, weakness_key=key, due_at=datetime.now(timezone.utc))
            db.add(card)
            rows[key] = card
    db.flush()
    return rows


def due_cards(db: Session, user: User, now: datetime | None = None) -> list[DueCard]:
    """Cards ready for review, most confident weakness first."""
    profile = load_profile(db, user.id)
    cards = ensure_cards(db, user)
    now = now or datetime.now(timezone.utc)

    due: list[DueCard] = []
    for key, card in cards.items():
        score = profile.get(key)
        if score is None or score.status == "retired":
            continue
        if not is_due(_card_state(card), now):
            continue
        due.append(
            DueCard(
                weakness_key=key,
                label=TAXONOMY[key].label if key in TAXONOMY else key,
                confidence=score.confidence,
                due_at=card.due_at,
                interval_days=card.interval_days,
                successes=card.successes,
                status=score.status,
            )
        )
    due.sort(key=lambda card: (-card.confidence, card.weakness_key))
    return due


def _pick_puzzle(db: Session, user: User, keys: list[str], attempted: set[str]) -> Puzzle | None:
    rating = user.current_rating_estimate
    low, high = rating - RATING_BELOW, rating + RATING_ABOVE

    for key in keys:
        query = select(Puzzle).where(Puzzle.taxonomy_keys.contains(key))
        candidates = [p for p in db.scalars(query).all() if p.id not in attempted]
        if not candidates:
            continue
        in_band = [p for p in candidates if low <= p.rating <= high]
        pool = in_band or candidates
        # Closest to the stretch target, which sits just above the current rating.
        target = rating + 50
        pool.sort(key=lambda p: abs(p.rating - target))
        return pool[0]
    return None


def next_puzzle(db: Session, user: User) -> tuple[Puzzle, str] | None:
    """The next puzzle and the weakness it targets."""
    attempted = {
        row.puzzle_id
        for row in db.scalars(
            select(PuzzleAttempt).where(PuzzleAttempt.user_id == user.id, PuzzleAttempt.correct.is_(True))
        ).all()
    }

    due = due_cards(db, user)
    ordered_keys = [card.weakness_key for card in due]
    if not ordered_keys:
        # Nothing due: fall back to any active weakness, then to the whole bank.
        profile = load_profile(db, user.id)
        ordered_keys = [
            key
            for key, score in sorted(profile.items(), key=lambda item: -item[1].confidence)
            if score.status != "retired"
        ]

    puzzle = _pick_puzzle(db, user, ordered_keys, attempted)
    if puzzle is not None:
        key = next((k for k in ordered_keys if k in puzzle.taxonomy_keys.split()), puzzle.taxonomy_keys.split()[0])
        return puzzle, key

    # No weakness-matched puzzle left: give them something at their level anyway.
    remaining = [p for p in db.scalars(select(Puzzle)).all() if p.id not in attempted]
    if not remaining:
        return None
    remaining.sort(key=lambda p: abs(p.rating - user.current_rating_estimate))
    chosen = remaining[0]
    return chosen, chosen.taxonomy_keys.split()[0]


def grade_puzzle(
    puzzle: Puzzle, answer: str, engine: StockfishEngine | None = None
) -> tuple[bool, str, int]:
    """Grade an attempt. Tactical puzzles need the move; concept puzzles allow a margin."""
    engine = engine or get_analysis_engine()
    board = chess.Board(puzzle.fen)

    expected_uci = puzzle.solution_moves.split()[0] if puzzle.solution_moves else ""
    try:
        played = board.parse_san(answer)
    except ValueError:
        try:
            played = chess.Move.from_uci(answer)
        except ValueError as exc:
            raise ValueError(f"{answer!r} is not a move.") from exc
    if played not in board.legal_moves:
        raise ValueError(f"{answer!r} is not legal in this position.")

    expected_san = puzzle.solution_san or (board.san(chess.Move.from_uci(expected_uci)) if expected_uci else "")
    if played.uci() == expected_uci:
        return True, expected_san, 0

    # Not the stored move: let the engine decide whether it is good enough anyway.
    correct, best_move, cp_loss = grade_answer(engine, puzzle.fen, board.san(played))
    within_tolerance = cp_loss <= puzzle.tolerance_cp
    return (correct and within_tolerance), expected_san or best_move, cp_loss


def record_puzzle_attempt(
    db: Session,
    user: User,
    puzzle: Puzzle,
    weakness_key: str,
    correct: bool,
    answer: str,
    seconds: float | None,
    context: str = "training",
) -> dict:
    """Store the attempt, advance the SRS card, and update the weakness profile."""
    db.add(
        PuzzleAttempt(
            user_id=user.id,
            puzzle_id=puzzle.id,
            weakness_key=weakness_key,
            context=context,
            correct=correct,
            played_move=answer[:12],
            time_ms=int(seconds * 1000) if seconds is not None else None,
        )
    )

    cards = ensure_cards(db, user)
    card = cards.get(weakness_key)
    if card is None:
        card = SrsCard(user_id=user.id, weakness_key=weakness_key, due_at=datetime.now(timezone.utc))
        db.add(card)
        db.flush()

    updated = review(_card_state(card), correct=correct, seconds=seconds)
    card.ease = updated.ease
    card.interval_days = updated.interval_days
    card.repetitions = updated.repetitions
    card.successes = updated.successes
    card.lapses = updated.lapses
    card.due_at = updated.due_at
    card.last_reviewed_at = datetime.now(timezone.utc)

    score = record_attempt_result(db, user.id, weakness_key, correct)
    status = _apply_retirement(db, user, weakness_key, updated)
    db.flush()

    return {
        "correct": correct,
        "weakness_key": weakness_key,
        "next_due_at": updated.due_at,
        "interval_days": updated.interval_days,
        "successes": updated.successes,
        "retired": status == "retired",
        "status": status,
        "confidence": score.confidence if score else 0.0,
    }


def _apply_retirement(db: Session, user: User, key: str, card: CardState) -> str:
    """Retire a weakness only after repeated success at growing intervals.

    The spaced-repetition card is the authority: it is the only thing that knows whether
    the successes were spread over time or crammed into one sitting.
    """
    profile = load_profile(db, user.id)
    current = profile.get(key)
    if current is None:
        return "active"

    if card.ready_to_retire and eligible_to_retire(current) and current.status != "retired":
        current.status = "retired"
        save_profile(db, user.id, profile)
        log.info("Retired weakness %s for user %s", key, user.id)
    elif current.status == "retired" and not card.ready_to_retire:
        # A lapse reopens it.
        current.status = "active"
        save_profile(db, user.id, profile)
    return current.status
