"""Stockfish, wrapped as the ground-truth analysis engine.

Stockfish is a referee, never a role model: it plays the objectively best move and has
no teaching style. Everything above this layer treats its output as fact and translates
it into human terms elsewhere.
"""
from __future__ import annotations

import threading

import chess
import chess.engine

from app.core.cache import Cache, get_cache
from app.core.config import settings
from app.core.logging import get_logger
from app.engines import boardlib as bl
from app.engines import motifs
from app.engines.lifecycle import register_closer
from app.engines.base import (
    MATE_FLOOR_LABEL,
    MATE_SCORE,
    AnalysisResult,
    EngineLine,
    MoveVerdict,
    at_least,
    classify_loss,
    win_probability,
)

# Evaluations at or beyond this magnitude mean a forced mate was found.
MATE_THRESHOLD = MATE_SCORE - 200

log = get_logger(__name__)

# Bounded search. Game review needs to be fast across many positions; a single
# deep-dive can afford more. Both are capped by time as well as depth so a pathological
# position cannot stall a request.
REVIEW_DEPTH = 14
REVIEW_SECONDS = 0.25
DEEP_DEPTH = 20
DEEP_SECONDS = 2.0
DEFAULT_MULTIPV = 3


class EngineUnavailable(RuntimeError):
    """Raised when no engine binary is usable. Callers must not silently guess."""


class StockfishEngine:
    """Thread-safe UCI wrapper with a result cache and automatic restart."""

    def __init__(
        self,
        path: str | None = None,
        depth: int = REVIEW_DEPTH,
        seconds: float = REVIEW_SECONDS,
        multipv: int = DEFAULT_MULTIPV,
        cache: Cache | None = None,
        threads: int = 1,
        hash_mb: int = 64,
    ) -> None:
        self.path = path or settings.resolved_stockfish_path()
        self.depth = depth
        self.seconds = seconds
        self.multipv = multipv
        self.threads = threads
        self.hash_mb = hash_mb
        self._cache = cache if cache is not None else get_cache()
        self._lock = threading.Lock()
        self._engine: chess.engine.SimpleEngine | None = None
        self._start()
        # Registered here rather than at the singleton accessor: any instance holds a
        # child process on a non-daemon thread, so any instance can hang the interpreter.
        register_closer(self.close)

    # ------------------------------------------------------------- lifecycle
    def _start(self) -> None:
        self._engine = None
        if not self.path:
            log.warning("No Stockfish binary found. Set STOCKFISH_PATH.")
            return
        try:
            engine = chess.engine.SimpleEngine.popen_uci(self.path)
            engine.configure({"Threads": self.threads, "Hash": self.hash_mb})
            self._engine = engine
            log.info("Stockfish ready at %s", self.path)
        except Exception as exc:
            log.error("Could not start Stockfish at %s: %s", self.path, exc)
            self._engine = None

    @property
    def available(self) -> bool:
        return self._engine is not None

    def close(self) -> None:
        with self._lock:
            if self._engine is not None:
                try:
                    self._engine.quit()
                except Exception:
                    pass
                self._engine = None

    # -------------------------------------------------------------- analysis
    def analyze(self, fen: str, depth: int | None = None, multipv: int | None = None) -> AnalysisResult:
        board = _validated_board(fen)
        depth = depth or self.depth
        multipv = multipv or self.multipv

        if board.is_game_over():
            return _terminal_result(board, depth)

        cache_key = f"analysis:v1:{board.fen()}:{depth}:{multipv}"
        cached = self._cache.get_json(cache_key)
        if cached:
            return _result_from_dict(cached)

        infos = self._analyse(board, depth, multipv)
        lines = _lines_from_infos(board, infos)
        if not lines:
            raise EngineUnavailable(f"Engine returned no move for {board.fen()}")

        result = AnalysisResult(fen=board.fen(), depth=depth, best=lines[0], top_moves=lines)
        self._cache.set_json(cache_key, _result_to_dict(result))
        return result

    def _analyse(self, board: chess.Board, depth: int, multipv: int) -> list[chess.engine.InfoDict]:
        limit = chess.engine.Limit(depth=depth, time=self.seconds)
        for attempt in (1, 2):
            if self._engine is None:
                with self._lock:
                    self._start()
            if self._engine is None:
                raise EngineUnavailable("Stockfish is not available; analysis cannot be trusted without it.")
            try:
                with self._lock:
                    infos = self._engine.analyse(board, limit, multipv=multipv)
                return infos if isinstance(infos, list) else [infos]
            except (chess.engine.EngineError, chess.engine.EngineTerminatedError) as exc:
                log.warning("Engine failed on %s (attempt %d): %s", board.fen(), attempt, exc)
                with self._lock:
                    self._start()
        raise EngineUnavailable(f"Stockfish failed twice on {board.fen()}")

    # ---------------------------------------------------------- move verdict
    def classify_move(
        self,
        fen: str,
        played_move: str,
        depth: int | None = None,
        context: motifs.MoveContext | None = None,
    ) -> MoveVerdict:
        """Judge one played move. Accepts SAN or UCI."""
        board = _validated_board(fen)
        move = _parse_move(board, played_move)
        played_san = board.san(move)

        before = self.analyze(board.fen(), depth=depth, multipv=max(2, self.multipv))
        best_move = chess.Move.from_uci(before.best.move_uci)
        eval_before = before.best.score_cp

        after_board = board.copy(stack=False)
        after_board.push(move)

        if move == best_move:
            eval_after = eval_before
        elif after_board.is_checkmate():
            eval_after = MATE_SCORE - 1
        elif after_board.is_game_over():
            eval_after = 0
        else:
            # Scores come back from the opponent's point of view; negate for the mover.
            reply = self.analyze(after_board.fen(), depth=depth, multipv=1)
            eval_after = -reply.best.score_cp

        cp_loss = max(0, eval_before - eval_after)
        wp_before = win_probability(eval_before)
        wp_after = win_probability(eval_after)
        wp_loss_pct = max(0.0, (wp_before - wp_after) * 100)
        label = classify_loss(cp_loss, wp_loss_pct, played_is_best=(move == best_move))

        # Forced mate overrides the win-probability softening in both directions.
        missed_forced_mate = eval_before >= MATE_THRESHOLD and eval_after < MATE_THRESHOLD
        allowed_forced_mate = eval_before > -MATE_THRESHOLD and eval_after <= -MATE_THRESHOLD
        if missed_forced_mate or allowed_forced_mate:
            label = at_least(label, MATE_FLOOR_LABEL)

        motif = motifs.DetectedMotif(None, [])
        if label in ("inaccuracy", "mistake", "blunder") or missed_forced_mate or allowed_forced_mate:
            best_line_moves = [chess.Move.from_uci(u) for u in before.best.pv_uci[1:]]
            motif = motifs.detect(board, move, best_move, best_line_moves, context)

        return MoveVerdict(
            fen=board.fen(),
            played_move=played_san,
            best_move=before.best.move_san,
            best_move_uci=before.best.move_uci,
            best_line=before.best.pv_san,
            eval_cp_before=eval_before,
            eval_cp_after=eval_after,
            cp_loss=cp_loss,
            win_prob_before=wp_before,
            win_prob_after=wp_after,
            win_prob_loss=wp_loss_pct,
            label=label,
            detected_motif=motif.motif,
            taxonomy_keys=motif.taxonomy_keys,
        )


# ------------------------------------------------------------------ helpers
def _validated_board(fen: str) -> chess.Board:
    """Reject impossible positions before they reach the engine.

    An illegal FEN (no king, side not to move already in check) crashes the Stockfish
    process rather than returning an error, so this guard is not optional.
    """
    try:
        board = chess.Board(fen)
    except ValueError as exc:
        raise ValueError(f"Malformed FEN: {fen}") from exc
    if not board.is_valid():
        raise ValueError(f"Illegal position ({board.status()!r}): {fen}")
    return board


def _parse_move(board: chess.Board, move: str) -> chess.Move:
    try:
        parsed = board.parse_san(move)
    except ValueError:
        try:
            parsed = chess.Move.from_uci(move)
        except ValueError as exc:
            raise ValueError(f"Unrecognised move {move!r} in {board.fen()}") from exc
    if parsed not in board.legal_moves:
        raise ValueError(f"Illegal move {move!r} in {board.fen()}")
    return parsed


def _lines_from_infos(board: chess.Board, infos: list[chess.engine.InfoDict]) -> list[EngineLine]:
    lines: list[EngineLine] = []
    for info in infos:
        pv = info.get("pv") or []
        score = info.get("score")
        if not pv or score is None:
            continue
        relative = score.relative
        lines.append(
            EngineLine(
                move_san=board.san(pv[0]),
                move_uci=pv[0].uci(),
                score_cp=relative.score(mate_score=MATE_SCORE) or 0,
                mate_in=relative.mate(),
                pv_san=_pv_to_san(board, pv[:10]),
                pv_uci=[m.uci() for m in pv[:10]],
            )
        )
    lines.sort(key=lambda line: line.score_cp, reverse=True)
    return lines


def _pv_to_san(board: chess.Board, pv: list[chess.Move]) -> list[str]:
    probe = board.copy(stack=False)
    san: list[str] = []
    for move in pv:
        if move not in probe.legal_moves:
            break
        san.append(probe.san(move))
        probe.push(move)
    return san


def _terminal_result(board: chess.Board, depth: int) -> AnalysisResult:
    score = -(MATE_SCORE - 1) if board.is_checkmate() else 0
    line = EngineLine(move_san="", move_uci="0000", score_cp=score, mate_in=0 if board.is_checkmate() else None)
    return AnalysisResult(fen=board.fen(), depth=depth, best=line, top_moves=[line])


def _result_to_dict(result: AnalysisResult) -> dict:
    return {
        "fen": result.fen,
        "depth": result.depth,
        "engine": result.engine,
        "lines": [
            {
                "move_san": line.move_san,
                "move_uci": line.move_uci,
                "score_cp": line.score_cp,
                "mate_in": line.mate_in,
                "pv_san": line.pv_san,
                "pv_uci": line.pv_uci,
            }
            for line in result.top_moves
        ],
    }


def _result_from_dict(data: dict) -> AnalysisResult:
    lines = [EngineLine(**line) for line in data["lines"]]
    return AnalysisResult(fen=data["fen"], depth=data["depth"], best=lines[0], top_moves=lines, engine=data["engine"])


# ------------------------------------------------------------------ singleton
_engine: StockfishEngine | None = None
_engine_lock = threading.Lock()


def get_analysis_engine() -> StockfishEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = StockfishEngine()
    return _engine
