"""Game import and playback."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RateLimit, get_current_user
from app.core.db import get_db
from app.core.logging import get_logger
from app.models import Game, User
from app.schemas.game import (
    GameDetail,
    GameSummary,
    ImportResult,
    MoveOut,
    PgnImportRequest,
    UsernameImportRequest,
)
from app.services.game_sources import GameSourceError, fetch_games
from app.services.pgn import ParsedGame, PgnError, parse_pgn, replay_fens, split_pgn_collection

log = get_logger(__name__)
router = APIRouter(prefix="/games", tags=["games"])

import_limit = RateLimit(limit=30, window_seconds=3600, name="game-import")


def _summary(game: Game, ply_count: int = 0) -> GameSummary:
    summary = GameSummary.model_validate(game)
    summary.ply_count = ply_count or len(game.moves)
    summary.outcome = _outcome(game.result, game.user_color)
    return summary


def _outcome(result: str | None, color: str) -> str:
    if result == "1/2-1/2":
        return "draw"
    if result == "1-0":
        return "win" if color == "white" else "loss"
    if result == "0-1":
        return "win" if color == "black" else "loss"
    return "unknown"


def _store(db: Session, user: User, parsed: ParsedGame, color: str, source: str) -> Game:
    game = Game(
        user_id=user.id,
        pgn=parsed.pgn,
        source=source,
        result=parsed.result,
        white=parsed.white,
        black=parsed.black,
        user_color=color,
        played_at=parsed.played_at,
        review_status="pending",
    )
    db.add(game)
    db.flush()
    return game


def _pick_color(parsed: ParsedGame, requested: str | None, hints: list[str]) -> str:
    if requested:
        return requested
    for hint in hints:
        found = parsed.color_for(hint)
        if found:
            return found
    return "white"


@router.post("/import/pgn", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
def import_pgn(
    payload: PgnImportRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _limit: None = Depends(import_limit),
) -> ImportResult:
    """Import one game, or every game in a multi-game PGN file."""
    texts = split_pgn_collection(payload.pgn) or [payload.pgn]
    hints = [h for h in (payload.player_name, user.display_name, user.email.split("@")[0]) if h]

    imported: list[GameSummary] = []
    skipped: list[str] = []
    for index, text in enumerate(texts, start=1):
        try:
            parsed = parse_pgn(text)
        except PgnError as exc:
            skipped.append(f"Game {index}: {exc}")
            continue
        color = _pick_color(parsed, payload.user_color, hints)
        game = _store(db, user, parsed, color, source="imported")
        imported.append(_summary(game, ply_count=parsed.ply_count))

    if not imported:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, skipped[0] if skipped else "No importable game found.")
    db.commit()
    return ImportResult(imported=imported, skipped=skipped)


@router.post("/import/username", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
def import_by_username(
    payload: UsernameImportRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _limit: None = Depends(import_limit),
) -> ImportResult:
    """Import recent public games for a Lichess or Chess.com account."""
    try:
        fetched = fetch_games(payload.platform, payload.username, payload.max_games)
    except GameSourceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    imported: list[GameSummary] = []
    skipped: list[str] = []
    for index, text in enumerate(fetched.pgns, start=1):
        try:
            parsed = parse_pgn(text)
        except PgnError as exc:
            skipped.append(f"Game {index}: {exc}")
            continue
        color = parsed.color_for(payload.username) or "white"
        game = _store(db, user, parsed, color, source="imported")
        imported.append(_summary(game, ply_count=parsed.ply_count))

    if not imported:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, skipped[0] if skipped else "No importable game found.")
    db.commit()
    return ImportResult(imported=imported, skipped=skipped)


@router.get("", response_model=list[GameSummary])
def list_games(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[GameSummary]:
    games = db.scalars(select(Game).where(Game.user_id == user.id).order_by(Game.id.desc())).all()
    summaries = []
    for game in games:
        try:
            ply_count = len(parse_pgn(game.pgn).moves)
        except PgnError:
            ply_count = 0
        summaries.append(_summary(game, ply_count=ply_count))
    return summaries


def _owned_game(game_id: int, user: User, db: Session) -> Game:
    game = db.get(Game, game_id)
    if game is None or game.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Game not found.")
    return game


@router.get("/{game_id}", response_model=GameDetail)
def get_game(game_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> GameDetail:
    game = _owned_game(game_id, user, db)
    try:
        parsed = parse_pgn(game.pgn)
        fens = replay_fens(game.pgn)
    except PgnError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    detail = GameDetail.model_validate(game)
    detail.ply_count = parsed.ply_count
    detail.outcome = _outcome(game.result, game.user_color)
    detail.moves = [
        MoveOut(ply=m.ply, move_number=m.move_number, side=m.side, san=m.san, uci=m.uci, fen_before=m.fen_before)
        for m in parsed.moves
    ]
    detail.fens = fens
    return detail


@router.delete("/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_game(game_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    game = _owned_game(game_id, user, db)
    db.delete(game)
    db.commit()
