"""The practice opponent.

Maia is a neural engine trained to imitate humans of a given rating: its mistakes are
the mistakes a person of that strength actually makes. A weakened Stockfish is not a
substitute -- it plays strong moves interrupted by random nonsense, which is confusing
to learn against. Where Maia is unavailable we say so through `opponent_kind` rather
than pretending.
"""
from __future__ import annotations

import random
import threading
from pathlib import Path

import chess
import chess.engine

from app.core.config import settings
from app.core.logging import get_logger
from app.engines.base import HumanMove
from app.engines.lifecycle import register_closer
from app.engines.stockfish import EngineUnavailable, _parse_move, _validated_board

log = get_logger(__name__)

# Maia publishes one network per rating band.
MAIA_BANDS: tuple[int, ...] = (1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900)

# Stockfish's own strength limiter does not go below this.
STOCKFISH_MIN_ELO = 1320
STOCKFISH_MAX_ELO = 2850


def nearest_band(rating: int, bands: tuple[int, ...] = MAIA_BANDS) -> int:
    return min(bands, key=lambda band: abs(band - rating))


class SparringService:
    """Picks the best available human-like opponent for a target rating."""

    def __init__(self, seed: int | None = None) -> None:
        self._lock = threading.Lock()
        self._maia: dict[int, chess.engine.SimpleEngine] = {}
        self._stockfish: chess.engine.SimpleEngine | None = None
        self._random = random.Random(seed)
        self.weights_dir = Path(settings.maia_weights_dir)

    # ------------------------------------------------------------------ maia
    def maia_weight_file(self, band: int) -> Path | None:
        candidate = self.weights_dir / f"maia-{band}.pb.gz"
        return candidate if candidate.exists() else None

    @property
    def maia_available(self) -> bool:
        if settings.resolved_lc0_path() is None:
            return False
        return any(self.maia_weight_file(band) for band in MAIA_BANDS)

    def _maia_engine(self, band: int) -> chess.engine.SimpleEngine | None:
        lc0 = settings.resolved_lc0_path()
        weights = self.maia_weight_file(band)
        if lc0 is None or weights is None:
            return None
        if band in self._maia:
            return self._maia[band]
        try:
            engine = chess.engine.SimpleEngine.popen_uci([lc0, f"--weights={weights}"])
            self._maia[band] = engine
            log.info("Maia %d ready (%s)", band, weights)
            return engine
        except Exception as exc:
            log.error("Could not start Maia %d: %s", band, exc)
            return None

    # ------------------------------------------------------------ stockfish
    def _stockfish_engine(self) -> chess.engine.SimpleEngine:
        if self._stockfish is not None:
            return self._stockfish
        path = settings.resolved_stockfish_path()
        if path is None:
            raise EngineUnavailable("No sparring engine available: neither lc0/Maia nor Stockfish was found.")
        engine = chess.engine.SimpleEngine.popen_uci(path)
        engine.configure({"Threads": 1, "Hash": 32})
        self._stockfish = engine
        return engine

    def _stockfish_move(self, board: chess.Board, rating: int) -> chess.Move:
        """Deliberately imperfect Stockfish, kept as honest as a limiter can be.

        Below Stockfish's own floor we sample from its top candidate moves, weighted so
        weaker targets pick worse moves more often. It is still not Maia.
        """
        engine = self._stockfish_engine()
        limit = chess.engine.Limit(depth=8, time=0.15)

        if rating >= STOCKFISH_MIN_ELO:
            elo = min(STOCKFISH_MAX_ELO, rating)
            try:
                engine.configure({"UCI_LimitStrength": True, "UCI_Elo": elo})
                result = engine.play(board, limit)
                if result.move is not None:
                    return result.move
            except chess.engine.EngineError as exc:
                log.warning("UCI_Elo %d rejected: %s", elo, exc)

        # Below the limiter's floor: sample among candidate moves.
        try:
            engine.configure({"UCI_LimitStrength": False})
        except chess.engine.EngineError:
            pass
        candidates = engine.analyse(board, limit, multipv=4)
        moves = [info["pv"][0] for info in candidates if info.get("pv")]
        if not moves:
            return next(iter(board.legal_moves))
        # 1100 picks the engine's favourite about half the time; stronger bands more often.
        top_bias = 0.45 + 0.35 * max(0.0, min(1.0, (rating - 700) / 600))
        weights = [top_bias if index == 0 else (1 - top_bias) / max(1, len(moves) - 1) for index in range(len(moves))]
        return self._random.choices(moves, weights=weights, k=1)[0]

    # --------------------------------------------------------------- public
    def get_human_move(self, fen: str, rating_band: int) -> HumanMove:
        board = _validated_board(fen)
        if board.is_game_over():
            raise ValueError("The game is already over; there is no move to make.")

        band = nearest_band(rating_band)
        with self._lock:
            engine = self._maia_engine(band)
            if engine is not None:
                # Maia's strength comes from its policy head: one node, no search.
                result = engine.play(board, chess.engine.Limit(nodes=1))
                if result.move is not None:
                    return HumanMove(
                        move_san=board.san(result.move),
                        move_uci=result.move.uci(),
                        opponent_kind="maia",
                        rating_band=band,
                    )
            move = self._stockfish_move(board, rating_band)

        return HumanMove(
            move_san=board.san(move),
            move_uci=move.uci(),
            opponent_kind="stockfish-limited",
            rating_band=rating_band,
        )

    def describe(self) -> dict[str, object]:
        bands = [band for band in MAIA_BANDS if self.maia_weight_file(band)]
        return {
            "opponent_kind": "maia" if self.maia_available else "stockfish-limited",
            "maia_available": self.maia_available,
            "lc0_path": settings.resolved_lc0_path(),
            "maia_bands": bands,
            "note": (
                "Playing against Maia, a network trained on human games."
                if self.maia_available
                else "Maia is not installed, so sparring uses a strength-limited Stockfish. "
                "It plays weaker, but less like a person. See engines/README.md."
            ),
        }

    def close(self) -> None:
        with self._lock:
            for engine in self._maia.values():
                try:
                    engine.quit()
                except Exception:
                    pass
            self._maia.clear()
            if self._stockfish is not None:
                try:
                    self._stockfish.quit()
                except Exception:
                    pass
                self._stockfish = None


_sparring: SparringService | None = None
_sparring_lock = threading.Lock()


def get_sparring_engine() -> SparringService:
    global _sparring
    with _sparring_lock:
        if _sparring is None:
            _sparring = SparringService()
            register_closer(_sparring.close)
    return _sparring


# Keep the helpers importable from this module too; they are part of the engine layer.
__all__ = ["MAIA_BANDS", "SparringService", "get_sparring_engine", "nearest_band", "_parse_move"]
