"""Game review and the weakness profile."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RateLimit, get_current_user
from app.core.db import SessionLocal, get_db
from app.core.logging import get_logger
from app.models import AnalyzedMove, Game, User
from app.schemas.weakness import ReviewedMoveOut, ReviewStatus, WeaknessOut
from app.services.jobs import get_job_runner
from app.services.review import review_game
from app.weakness.service import apply_evidence, load_profile
from app.weakness.taxonomy import label as taxonomy_label

log = get_logger(__name__)
router = APIRouter(tags=["review"])

review_limit = RateLimit(limit=40, window_seconds=3600, name="game-review")


def _job_id(game_id: int) -> str:
    return f"review:{game_id}"


def run_review_job(game_id: int, user_id: int, job_id: str | None = None) -> dict[str, object]:
    """Executed on the worker pool: its own session, its own engine handle."""
    runner = get_job_runner()
    with SessionLocal() as db:
        game = db.get(Game, game_id)
        if game is None or game.user_id != user_id:
            raise ValueError("Game not found")
        game.review_status = "running"
        db.commit()

        try:
            outcome = review_game(db, game, progress=runner, job_id=job_id)
            apply_evidence(db, user_id, outcome.evidence)
            db.commit()
        except Exception:
            db.rollback()
            failed = db.get(Game, game_id)
            if failed is not None:
                failed.review_status = "failed"
                db.commit()
            raise

        return {
            "game_id": game_id,
            "moves_reviewed": outcome.moves_reviewed,
            "accuracy": outcome.accuracy,
            "label_counts": outcome.label_counts,
            "weaknesses_found": len({e.taxonomy_key for e in outcome.evidence}),
        }


def _owned_game(game_id: int, user: User, db: Session) -> Game:
    game = db.get(Game, game_id)
    if game is None or game.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Game not found.")
    return game


@router.post("/games/{game_id}/review", response_model=ReviewStatus, status_code=status.HTTP_202_ACCEPTED)
def start_review(
    game_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _limit: None = Depends(review_limit),
) -> ReviewStatus:
    game = _owned_game(game_id, user, db)
    runner = get_job_runner()
    job_id = _job_id(game_id)

    if runner.is_running(job_id):
        return ReviewStatus(game_id=game_id, state="running", **runner.status(job_id).get("counts", {}))

    game.review_status = "queued"
    db.commit()
    runner.submit(job_id, run_review_job, game_id, user.id)
    return ReviewStatus(game_id=game_id, state="queued")


@router.get("/games/{game_id}/review", response_model=ReviewStatus)
def get_review(game_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ReviewStatus:
    game = _owned_game(game_id, user, db)
    job = get_job_runner().status(_job_id(game_id))

    moves = db.scalars(
        select(AnalyzedMove).where(AnalyzedMove.game_id == game_id).order_by(AnalyzedMove.ply)
    ).all()

    state = game.review_status
    if job.get("state") in ("queued", "running", "failed"):
        state = str(job["state"])
    elif moves:
        state = "done"

    label_counts: dict[str, int] = {}
    for move in moves:
        label_counts[move.move_label] = label_counts.get(move.move_label, 0) + 1

    return ReviewStatus(
        game_id=game_id,
        state=state,
        progress=int(job.get("progress", 0) or 0),
        total=int(job.get("total", 0) or 0),
        accuracy=game.accuracy,
        label_counts=label_counts,
        error=job.get("error"),
        moves=[_move_out(move) for move in moves],
    )


def _move_out(move: AnalyzedMove) -> ReviewedMoveOut:
    keys = [key for key in move.taxonomy_keys.split(",") if key]
    return ReviewedMoveOut(
        ply=move.ply,
        move_number=move.move_number,
        side=move.side,
        fen=move.fen,
        played_move=move.played_move,
        best_move=move.best_move,
        best_move_uci=move.best_move_uci or "",
        best_line=move.best_line.split() if move.best_line else [],
        eval_cp_before=move.eval_cp_before,
        eval_cp_after=move.eval_cp_after,
        cp_loss=move.cp_loss,
        win_prob_loss=move.win_prob_loss,
        move_label=move.move_label,
        detected_motif=move.detected_motif,
        taxonomy_keys=keys,
        taxonomy_labels=[taxonomy_label(key) for key in keys],
    )


@router.get("/weaknesses", response_model=list[WeaknessOut])
def get_weaknesses(
    include_retired: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WeaknessOut]:
    profile = load_profile(db, user.id)
    scores = [
        score
        for score in profile.values()
        if include_retired or score.status != "retired"
    ]
    scores.sort(key=lambda score: (-score.confidence, score.taxonomy_key))
    return [WeaknessOut.from_score(score) for score in scores]
