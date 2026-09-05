"""Practice games against a human-like opponent, with a coached review afterwards.

The opponent comes from `app.engines.sparring`: Maia when it is installed, a
strength-limited Stockfish otherwise. Which one is in use is reported to the learner
rather than hidden, because a limited Stockfish plays weaker but less like a person.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime, timezone

import chess
import chess.pgn
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.engines.base import HumanMove
from app.engines.sparring import SparringService, get_sparring_engine
from app.models import Game, User

log = get_logger(__name__)

MAX_PLIES = 400


@dataclass
class PracticeState:
    game_id: int
    fen: str
    pgn: str
    user_color: str
    turn: str
    move_history: list[str]
    last_move_uci: str | None
    is_over: bool
    result: str | None
    outcome_text: str
    opponent_kind: str
    opponent_rating: int
    in_check: bool
    legal_move_count: int


def _board_from(game: Game) -> chess.Board:
    parsed = chess.pgn.read_game(io.StringIO(game.pgn))
    board = chess.Board()
    if parsed is not None:
        for move in parsed.mainline_moves():
            board.push(move)
    return board


def _history(game: Game) -> list[str]:
    parsed = chess.pgn.read_game(io.StringIO(game.pgn))
    if parsed is None:
        return []
    board = chess.Board()
    moves = []
    for move in parsed.mainline_moves():
        moves.append(board.san(move))
        board.push(move)
    return moves


def _write_pgn(
    game: Game, board: chess.Board, user: User, opponent_label: str, result: str | None = None
) -> str:
    """Rebuild the PGN from the move stack so headers and result stay accurate.

    `result` overrides the board's own result, which is what a resignation needs: the
    position is not over, but the game is.
    """
    exported = chess.pgn.Game()
    exported.headers["Event"] = "Practice game"
    exported.headers["Site"] = "GrandmasterAI"
    exported.headers["Date"] = datetime.now(timezone.utc).strftime("%Y.%m.%d")
    exported.headers["White"] = user.display_name if game.user_color == "white" else opponent_label
    exported.headers["Black"] = opponent_label if game.user_color == "white" else user.display_name
    exported.headers["Result"] = result or board.result(claim_draw=True)

    node: chess.pgn.GameNode = exported
    for move in board.move_stack:
        node = node.add_variation(move)
    return str(exported)


def _outcome_text(board: chess.Board, user_color: str) -> str:
    if not board.is_game_over(claim_draw=True):
        return ""
    if board.is_checkmate():
        winner = "black" if board.turn == chess.WHITE else "white"
        return "You won by checkmate." if winner == user_color else "You were checkmated."
    if board.is_stalemate():
        return "Stalemate. The game is a draw."
    if board.is_insufficient_material():
        return "Neither side has enough material to mate. Draw."
    if board.can_claim_fifty_moves():
        return "Fifty moves without a capture or pawn move. Draw."
    if board.can_claim_threefold_repetition():
        return "The position repeated three times. Draw."
    return "The game is over."


def _state(
    game: Game,
    board: chess.Board,
    opponent_kind: str,
    opponent_rating: int,
    last_move: str | None = None,
) -> PracticeState:
    over = board.is_game_over(claim_draw=True)
    return PracticeState(
        game_id=game.id,
        fen=board.fen(),
        pgn=game.pgn,
        user_color=game.user_color,
        turn="white" if board.turn == chess.WHITE else "black",
        move_history=_history(game),
        last_move_uci=last_move,
        is_over=over,
        result=board.result(claim_draw=True) if over else None,
        outcome_text=_outcome_text(board, game.user_color),
        opponent_kind=opponent_kind,
        opponent_rating=opponent_rating,
        in_check=board.is_check(),
        legal_move_count=board.legal_moves.count(),
    )


def start_game(
    db: Session, user: User, color: str = "white", sparring: SparringService | None = None
) -> tuple[Game, PracticeState]:
    sparring = sparring or get_sparring_engine()
    rating = user.current_rating_estimate
    described = sparring.describe()
    opponent_label = f"Coach bot ({described['opponent_kind']} ~{rating})"

    game = Game(
        user_id=user.id,
        pgn="",
        source="practice",
        user_color=color,
        white=user.display_name if color == "white" else opponent_label,
        black=opponent_label if color == "white" else user.display_name,
        review_status="pending",
        played_at=datetime.now(timezone.utc),
    )
    db.add(game)
    db.flush()

    board = chess.Board()
    last_move = None
    if color == "black":
        # The opponent has the first move.
        reply = sparring.get_human_move(board.fen(), rating)
        board.push_uci(reply.move_uci)
        last_move = reply.move_uci

    game.pgn = _write_pgn(game, board, user, opponent_label)
    db.flush()

    return game, _state(game, board, str(described["opponent_kind"]), rating, last_move)


def play_move(
    db: Session, user: User, game: Game, move: str, sparring: SparringService | None = None
) -> PracticeState:
    """Apply the learner's move, then the opponent's reply."""
    sparring = sparring or get_sparring_engine()
    board = _board_from(game)

    if board.is_game_over(claim_draw=True):
        raise ValueError("This game is already finished.")
    if len(board.move_stack) >= MAX_PLIES:
        raise ValueError("This game has gone on too long; start a new one.")

    expected_turn = chess.WHITE if game.user_color == "white" else chess.BLACK
    if board.turn != expected_turn:
        raise ValueError("It is not your turn.")

    try:
        parsed = board.parse_san(move)
    except ValueError:
        try:
            parsed = chess.Move.from_uci(move)
        except ValueError as exc:
            raise ValueError(f"{move!r} is not a move.") from exc
    if parsed not in board.legal_moves:
        raise ValueError(f"{move!r} is not legal in this position.")

    board.push(parsed)
    last_move = parsed.uci()
    rating = user.current_rating_estimate
    described = sparring.describe()

    if not board.is_game_over(claim_draw=True):
        reply: HumanMove = sparring.get_human_move(board.fen(), rating)
        board.push_uci(reply.move_uci)
        last_move = reply.move_uci

    opponent_label = game.black if game.user_color == "white" else game.white
    game.pgn = _write_pgn(game, board, user, opponent_label or "Coach bot")
    if board.is_game_over(claim_draw=True):
        game.result = board.result(claim_draw=True)
    db.flush()

    return _state(game, board, str(described["opponent_kind"]), rating, last_move)


def resign(db: Session, user: User, game: Game) -> PracticeState:
    board = _board_from(game)
    game.result = "0-1" if game.user_color == "white" else "1-0"
    opponent_label = game.black if game.user_color == "white" else game.white
    game.pgn = _write_pgn(game, board, user, opponent_label or "Coach bot", result=game.result)
    db.flush()

    described = get_sparring_engine().describe()
    state = _state(game, board, str(described["opponent_kind"]), user.current_rating_estimate)
    state.is_over = True
    state.result = game.result
    state.outcome_text = "You resigned."
    return state


def current_state(db: Session, user: User, game: Game) -> PracticeState:
    board = _board_from(game)
    described = get_sparring_engine().describe()
    state = _state(game, board, str(described["opponent_kind"]), user.current_rating_estimate)
    if game.result and not state.is_over:
        state.is_over = True
        state.result = game.result
        state.outcome_text = "This game was resigned."
    return state
