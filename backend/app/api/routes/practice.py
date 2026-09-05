"""Practice games against the sparring opponent."""
from __future__ import annotations

import random

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RateLimit, get_current_user
from app.api.routes.review import run_review_job
from app.core.db import get_db
from app.engines.sparring import get_sparring_engine
from app.models import Game, User
from app.practice import service
from app.schemas.practice import MoveRequest, NewGameRequest, PracticeStateOut
from app.services.jobs import get_job_runner

router = APIRouter(prefix="/practice", tags=["practice"])

move_limit = RateLimit(limit=600, window_seconds=3600, name="practice-move")
new_game_limit = RateLimit(limit=30, window_seconds=3600, name="practice-new")


def _out(state: service.PracticeState, review_status: str = "pending") -> PracticeStateOut:
    note = str(get_sparring_engine().describe()["note"])
    return PracticeStateOut(
        game_id=state.game_id,
        fen=state.fen,
        user_color=state.user_color,
        turn=state.turn,
        move_history=state.move_history,
        last_move_uci=state.last_move_uci,
        is_over=state.is_over,
        result=state.result,
        outcome_text=state.outcome_text,
        opponent_kind=state.opponent_kind,
        opponent_rating=state.opponent_rating,
        opponent_note=note,
        in_check=state.in_check,
        legal_move_count=state.legal_move_count,
        review_status=review_status,
    )


def _owned_practice_game(game_id: int, user: User, db: Session) -> Game:
    game = db.get(Game, game_id)
    if game is None or game.user_id != user.id or game.source != "practice":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Practice game not found.")
    return game


def _queue_review(game: Game, user: User) -> None:
    """A finished practice game is reviewed straight away, so coaching is waiting."""
    if not game.pgn.strip():
        return
    game.review_status = "queued"
    get_job_runner().submit(f"review:{game.id}", run_review_job, game.id, user.id)


@router.post("/new", response_model=PracticeStateOut, status_code=status.HTTP_201_CREATED)
def new_game(
    payload: NewGameRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _limit: None = Depends(new_game_limit),
) -> PracticeStateOut:
    color = payload.color if payload.color != "random" else random.choice(["white", "black"])
    _game, state = service.start_game(db, user, color)
    db.commit()
    return _out(state)


@router.get("/current", response_model=PracticeStateOut | None)
def current_game(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> PracticeStateOut | None:
    """The most recent practice game, finished or not.

    A finished game must still be returned: the learner needs to see the result and the
    link to its review, which arrives seconds later.
    """
    game = db.scalar(
        select(Game)
        .where(Game.user_id == user.id, Game.source == "practice")
        .order_by(Game.id.desc())
        .limit(1)
    )
    if game is None:
        return None
    return _out(service.current_state(db, user, game), game.review_status)


@router.get("/{game_id}", response_model=PracticeStateOut)
def get_game(game_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> PracticeStateOut:
    game = _owned_practice_game(game_id, user, db)
    return _out(service.current_state(db, user, game), game.review_status)


@router.post("/{game_id}/move", response_model=PracticeStateOut)
def play_move(
    game_id: int,
    payload: MoveRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _limit: None = Depends(move_limit),
) -> PracticeStateOut:
    game = _owned_practice_game(game_id, user, db)
    try:
        state = service.play_move(db, user, game, payload.move)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    if state.is_over:
        _queue_review(game, user)
    db.commit()
    return _out(state, game.review_status)


@router.post("/{game_id}/resign", response_model=PracticeStateOut)
def resign(game_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> PracticeStateOut:
    game = _owned_practice_game(game_id, user, db)
    state = service.resign(db, user, game)
    _queue_review(game, user)
    db.commit()
    return _out(state, game.review_status)
