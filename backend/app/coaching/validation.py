"""Guardrails on anything the coaching brain produces.

The model writes the teaching; it does not get to decide chess facts. Every position it
invents is checked for legality and every answer it proposes is re-derived from the
engine. If the two disagree, the engine wins.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import chess

from app.core.logging import get_logger
from app.engines.stockfish import StockfishEngine

log = get_logger(__name__)

# A student's move counts as correct when it is this close to the engine's best.
ANSWER_MARGIN_CP = 50


@dataclass
class GroundedAnswer:
    fen: str
    answer_san: str
    answer_uci: str
    corrected: bool  # True when the model's proposed answer was not the engine's choice
    proposed: str | None = None


@dataclass
class ValidationReport:
    ok: bool
    problems: list[str] = field(default_factory=list)


def legal_position(fen: str) -> bool:
    try:
        board = chess.Board(fen)
    except ValueError:
        return False
    return board.is_valid() and not board.is_game_over()


def legal_move(fen: str, move: str) -> str | None:
    """Return the move in SAN if it is legal in the position, else None."""
    try:
        board = chess.Board(fen)
    except ValueError:
        return None
    if not board.is_valid():
        return None
    for parser in (board.parse_san, lambda m: chess.Move.from_uci(m)):
        try:
            parsed = parser(move)
        except ValueError:
            continue
        if parsed in board.legal_moves:
            return board.san(parsed)
    return None


def ground_answer(engine: StockfishEngine, fen: str, proposed: str | None) -> GroundedAnswer | None:
    """Decide the objectively correct answer for a position.

    The model's suggestion is only a hint. The engine's best move is the key, so a
    comprehension check can never be marked against something the model got wrong.
    """
    if not legal_position(fen):
        return None
    try:
        analysis = engine.analyze(fen, multipv=1)
    except Exception as exc:
        log.warning("Could not ground the answer for %s: %s", fen, exc)
        return None
    if not analysis.best.move_uci or analysis.best.move_uci == "0000":
        return None

    proposed_san = legal_move(fen, proposed) if proposed else None
    corrected = proposed_san is not None and proposed_san != analysis.best.move_san
    if proposed_san is None and proposed:
        corrected = True
    return GroundedAnswer(
        fen=fen,
        answer_san=analysis.best.move_san,
        answer_uci=analysis.best.move_uci,
        corrected=corrected,
        proposed=proposed,
    )


def grade_answer(engine: StockfishEngine, fen: str, student_move: str) -> tuple[bool, str, int]:
    """Grade a student's answer against the engine, not against the model's key.

    Returns (correct, best_move_san, centipawns_lost). Any move within
    `ANSWER_MARGIN_CP` of the best counts, so a second good move is not marked wrong.
    """
    verdict = engine.classify_move(fen, student_move)
    correct = verdict.cp_loss <= ANSWER_MARGIN_CP
    return correct, verdict.best_move, verdict.cp_loss


def validate_lesson(lesson: dict, engine: StockfishEngine) -> tuple[dict, ValidationReport]:
    """Check and repair a generated lesson. Returns the cleaned lesson and a report."""
    problems: list[str] = []
    cleaned = dict(lesson)

    examples = []
    for index, example in enumerate(lesson.get("examples", []), start=1):
        fen = str(example.get("fen", ""))
        move = str(example.get("move", ""))
        if not legal_position(fen):
            problems.append(f"Example {index} used an illegal position and was dropped.")
            continue
        san = legal_move(fen, move)
        if san is None:
            grounded = ground_answer(engine, fen, move)
            if grounded is None:
                problems.append(f"Example {index} used an illegal move and was dropped.")
                continue
            problems.append(f"Example {index} proposed the illegal move {move!r}; used {grounded.answer_san} instead.")
            san = grounded.answer_san
        examples.append({**example, "fen": fen, "move": san})
    cleaned["examples"] = examples

    check = lesson.get("check") or {}
    fen = str(check.get("fen", ""))
    grounded = ground_answer(engine, fen, str(check.get("answer", "")) or None)
    if grounded is None:
        problems.append("The comprehension check position was unusable and was removed.")
        cleaned["check"] = None
    else:
        if grounded.corrected:
            problems.append(
                f"The check answer {check.get('answer')!r} was not the engine's choice; "
                f"the key is {grounded.answer_san}."
            )
        cleaned["check"] = {
            **check,
            "fen": fen,
            "answer": grounded.answer_san,
            "answer_uci": grounded.answer_uci,
        }

    ok = bool(cleaned["examples"]) and cleaned["check"] is not None
    if not ok:
        problems.append("The lesson had no usable example or check.")
    return cleaned, ValidationReport(ok=ok, problems=problems)
