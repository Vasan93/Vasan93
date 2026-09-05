"""Game review: label every move the learner played and turn mistakes into evidence.

The engine decides what was wrong. This module decides what *kind* of wrong it was, in
taxonomy terms, and hands that to the weakness model.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import chess
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.engines import boardlib as bl
from app.engines.motifs import MoveContext
from app.engines.stockfish import StockfishEngine, get_analysis_engine
from app.models import AnalyzedMove, Game
from app.services.pgn import ParsedGame, parse_pgn
from app.weakness.model import Evidence

log = get_logger(__name__)

MISTAKE_LABELS = ("inaccuracy", "mistake", "blunder")


@dataclass
class ReviewOutcome:
    game_id: int
    moves_reviewed: int
    accuracy: float
    label_counts: dict[str, int]
    evidence: list[Evidence]


def move_accuracy(win_prob_loss_pct: float) -> float:
    """Accuracy for one move, from how much win probability it gave away.

    The curve is the one Lichess uses: near-perfect moves score ~100, and accuracy falls
    away steeply as the win probability drops.
    """
    value = 103.1668 * math.exp(-0.04354 * max(0.0, win_prob_loss_pct)) - 3.1669
    # The curve peaks a hair under 100; round so a perfect move reads as 100.0.
    return round(max(0.0, min(100.0, value)), 1)


def _contexts(parsed: ParsedGame, color: str) -> dict[int, MoveContext]:
    """Per-ply context: phase, history and whether the learner has castled yet."""
    board = chess.Board()
    history: list[chess.Move] = []
    castled = False
    contexts: dict[int, MoveContext] = {}

    for move in parsed.moves:
        engine_move = chess.Move.from_uci(move.uci)
        if move.side == color:
            contexts[move.ply] = MoveContext(
                move_number=move.move_number,
                phase=bl.game_phase(board),
                history=[m for m in history],
                castling_done=castled,
            )
        if move.side == color and board.is_castling(engine_move):
            castled = True
        history.append(engine_move)
        board.push(engine_move)
    return contexts


def review_game(
    db: Session,
    game: Game,
    engine: StockfishEngine | None = None,
    depth: int | None = None,
    progress: object | None = None,
    job_id: str | None = None,
) -> ReviewOutcome:
    """Analyse every move the learner played and store the verdicts."""
    engine = engine or get_analysis_engine()
    parsed = parse_pgn(game.pgn)
    color = game.user_color
    contexts = _contexts(parsed, color)
    own_moves = [move for move in parsed.moves if move.side == color]

    # A re-review replaces the previous one rather than duplicating it.
    db.execute(delete(AnalyzedMove).where(AnalyzedMove.game_id == game.id))

    label_counts: dict[str, int] = {}
    evidence: list[Evidence] = []
    accuracies: list[float] = []

    for index, move in enumerate(own_moves, start=1):
        verdict = engine.classify_move(
            move.fen_before, move.san, depth=depth, context=contexts.get(move.ply)
        )
        label_counts[verdict.label] = label_counts.get(verdict.label, 0) + 1
        accuracies.append(move_accuracy(verdict.win_prob_loss))

        db.add(
            AnalyzedMove(
                game_id=game.id,
                ply=move.ply,
                move_number=move.move_number,
                side=move.side,
                fen=move.fen_before,
                played_move=verdict.played_move,
                best_move=verdict.best_move,
                best_move_uci=verdict.best_move_uci,
                best_line=" ".join(verdict.best_line[:8]),
                eval_cp_before=verdict.eval_cp_before,
                eval_cp_after=verdict.eval_cp_after,
                cp_loss=verdict.cp_loss,
                win_prob_loss=verdict.win_prob_loss,
                move_label=verdict.label,
                detected_motif=verdict.detected_motif,
                taxonomy_keys=",".join(verdict.taxonomy_keys),
            )
        )

        if verdict.label in MISTAKE_LABELS:
            for key in verdict.taxonomy_keys:
                evidence.append(Evidence(taxonomy_key=key, label=verdict.label, game_id=game.id, ply=move.ply))

        if progress is not None and job_id is not None:
            progress.report_progress(job_id, index, len(own_moves))  # type: ignore[attr-defined]

    accuracy = round(sum(accuracies) / len(accuracies), 1) if accuracies else 0.0
    game.accuracy = accuracy
    game.review_status = "done"
    db.flush()

    return ReviewOutcome(
        game_id=game.id,
        moves_reviewed=len(own_moves),
        accuracy=accuracy,
        label_counts=label_counts,
        evidence=evidence,
    )
