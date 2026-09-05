"""Turn an engine verdict into a named motif and taxonomy keys.

The engine says *how much* a move lost. This module says *what kind of mistake* it was,
which is what the weakness model and the curriculum actually need.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import chess

from app.engines import boardlib as bl


@dataclass(frozen=True)
class MoveContext:
    """Everything known about a move beyond the position itself."""

    move_number: int = 1
    phase: str = "middlegame"
    history: list[chess.Move] = field(default_factory=list)  # moves played before this one
    castling_done: bool = False


@dataclass(frozen=True)
class DetectedMotif:
    motif: str | None
    taxonomy_keys: list[str]


_EMPTY = DetectedMotif(None, [])


def _mate_in_line(board: chess.Board, line: list[chess.Move]) -> chess.Board | None:
    """Play a principal variation out and return the final board if it ends in mate."""
    probe = board.copy(stack=False)
    for move in line[:12]:
        if move not in probe.legal_moves:
            return None
        probe.push(move)
        if probe.is_checkmate():
            return probe
    return None


def _opening_motif(board: chess.Board, move: chess.Move, ctx: MoveContext) -> DetectedMotif | None:
    """Opening-principle violations. Needs move-number and history context."""
    if ctx.phase != "opening":
        return None
    mover = board.turn
    piece = board.piece_at(move.from_square)
    if piece is None:
        return None

    home_rank = 0 if mover == chess.WHITE else 7

    # Early queen sortie: the queen leaves home before the minor pieces are out.
    if piece.piece_type == chess.QUEEN and ctx.move_number <= 6:
        if bl.undeveloped_minor_count(board, mover) >= 3:
            return DetectedMotif("early_queen", ["opening_principles", "piece_development"])

    # Moving the same piece twice while pieces sit at home.
    if ctx.history:
        recent = [m for m in ctx.history[-6:] if m.to_square == move.from_square]
        if recent and bl.undeveloped_minor_count(board, mover) >= 2 and piece.piece_type != chess.PAWN:
            return DetectedMotif("same_piece_twice", ["opening_principles", "piece_development"])

    # Castling long overdue with the king still at home.
    king_square = board.king(mover)
    if (
        ctx.move_number >= 9
        and not ctx.castling_done
        and king_square is not None
        and chess.square_rank(king_square) == home_rank
        and board.has_castling_rights(mover)
        and not board.is_castling(move)
    ):
        return DetectedMotif("castling_delayed", ["king_safety", "opening_principles"])

    # Ignoring development entirely.
    if bl.undeveloped_minor_count(board, mover) >= 3 and not bl.is_developing_move(board, move):
        if piece.piece_type == chess.PAWN and ctx.move_number >= 4:
            return DetectedMotif("development_ignored", ["piece_development", "center_control"])

    return None


def _endgame_motif(board: chess.Board, move: chess.Move, best_move: chess.Move) -> DetectedMotif | None:
    """Endgame-specific patterns, judged against what the engine wanted instead."""
    mover = board.turn
    king_square = board.king(mover)
    if king_square is None:
        return None

    best_piece = board.piece_at(best_move.from_square)
    played_piece = board.piece_at(move.from_square)

    only_pawns = bl.non_pawn_material(board) == 0
    rooks_on = bool(board.pieces(chess.ROOK, chess.WHITE) or board.pieces(chess.ROOK, chess.BLACK))

    # The engine wanted a king move and got something else: passive king.
    if best_piece and best_piece.piece_type == chess.KING and (played_piece is None or played_piece.piece_type != chess.KING):
        if only_pawns:
            return DetectedMotif("passive_king", ["opposition", "king_activity_endgame"])
        return DetectedMotif("passive_king", ["king_activity_endgame"])

    # Pushing a pawn when the engine wanted the king to escort it.
    if played_piece and played_piece.piece_type == chess.PAWN and only_pawns:
        return DetectedMotif("pawn_pushed_too_early", ["pawn_promotion", "opposition"])

    if rooks_on and played_piece and played_piece.piece_type == chess.ROOK:
        return DetectedMotif("rook_misplaced", ["rook_endgames"])

    if board.pieces(chess.QUEEN, mover) or board.pieces(chess.ROOK, mover):
        opponent_material = sum(
            len(board.pieces(pt, not mover)) for pt in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
        )
        if opponent_material == 0:
            return DetectedMotif("conversion_failure", ["basic_checkmates"])

    return None


def detect(
    board: chess.Board,
    played: chess.Move,
    best: chess.Move,
    best_line: list[chess.Move],
    context: MoveContext | None = None,
) -> DetectedMotif:
    """Name the mistake. `board` is the position before the played move."""
    ctx = context or MoveContext(phase=bl.game_phase(board))
    mover = board.turn

    if played == best:
        return _EMPTY

    after_played = board.copy(stack=False)
    after_played.push(played)

    # ---- forced mate, in either direction: the highest-value signal there is
    mate_board = _mate_in_line(board, [best, *best_line])
    if mate_board is not None:
        keys = ["missed_mate"]
        if bl.is_back_rank_mate(mate_board):
            keys.append("back_rank")
        return DetectedMotif("missed_mate", keys)

    if after_played.is_checkmate():
        return _EMPTY  # the played move delivered mate
    if _mate_in_line(after_played, _shallow_best_line(after_played)) is not None:
        keys = ["allowed_mate", "threat_checking"]
        return DetectedMotif("allowed_mate", keys)

    # ---- material left en prise by the played move
    hanging_before = bl.worst_hanging(board, mover)
    hanging_after = bl.worst_hanging(after_played, mover)
    if hanging_after >= 100 and hanging_after > hanging_before:
        keys = ["hanging_pieces", "threat_checking"]
        if bl.creates_fork(after_played, played) is False and hanging_after >= 300:
            keys.append("threat_checking")
        return DetectedMotif("hung_piece", list(dict.fromkeys(keys)))

    # ---- material the best move would have won
    after_best = board.copy(stack=False)
    after_best.push(best)

    if board.is_capture(best) and bl.static_exchange_eval(board, best) >= 100 and not board.is_capture(played):
        return DetectedMotif("missed_capture", ["missed_captures", "hanging_pieces"])

    if bl.creates_fork(after_best, best):
        return DetectedMotif("missed_fork", ["missed_forks"])

    pin_kind = bl.creates_pin_or_skewer(after_best, best)
    if pin_kind:
        return DetectedMotif(f"missed_{pin_kind}", ["missed_pins_skewers"])

    if bl.creates_discovered_attack(board, best):
        return DetectedMotif("missed_discovered_attack", ["missed_discovered_attacks"])

    # ---- the opponent's last move carried a threat that went unanswered
    if hanging_before >= 200 and hanging_after >= 200:
        return DetectedMotif("threat_ignored", ["threat_checking", "hanging_pieces"])

    # ---- phase-specific quiet mistakes
    opening = _opening_motif(board, played, ctx)
    if opening:
        return opening

    if ctx.phase == "endgame":
        endgame = _endgame_motif(board, played, best)
        if endgame:
            return endgame

    # ---- king safety in the middlegame
    if ctx.phase == "middlegame":
        king_square = board.king(mover)
        if king_square is not None and board.has_castling_rights(mover):
            return DetectedMotif("king_left_in_centre", ["king_safety"])
        moved = board.piece_at(played.from_square)
        if moved and moved.piece_type == chess.PAWN and king_square is not None:
            if chess.square_distance(played.to_square, king_square) <= 2:
                return DetectedMotif("pawn_shield_weakened", ["king_safety", "pawn_structure"])

    return DetectedMotif("positional_slip", ["piece_activity"])


def _shallow_best_line(board: chess.Board) -> list[chess.Move]:
    """A cheap forced-mate probe: only checks and captures, no engine call.

    Full mate detection belongs to the engine; this catches the obvious one-and
    two-move mates the opponent is about to land.
    """
    line: list[chess.Move] = []
    probe = board.copy(stack=False)
    for _ in range(3):
        forcing = [m for m in probe.legal_moves if probe.gives_check(m)]
        mate = next((m for m in forcing if _is_mate_after(probe, m)), None)
        if mate is not None:
            line.append(mate)
            return line
        return []
    return line


def _is_mate_after(board: chess.Board, move: chess.Move) -> bool:
    board.push(move)
    result = board.is_checkmate()
    board.pop()
    return result
