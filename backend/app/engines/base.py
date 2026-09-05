"""The internal engine interface.

Nothing outside this package talks to an engine binary. Everything above it consumes
these dataclasses, so Stockfish, Maia or a stub are interchangeable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

# Mate scores are folded into centipawns so a single integer orders every evaluation:
# mate in 1 for the mover is +9999, mate in 3 is +9997, mate against is negative.
MATE_SCORE = 10_000


@dataclass(frozen=True)
class EngineLine:
    """One candidate move with its evaluation, from the point of view of the side to move."""

    move_san: str
    move_uci: str
    score_cp: int
    mate_in: int | None
    pv_san: list[str] = field(default_factory=list)
    pv_uci: list[str] = field(default_factory=list)

    @property
    def is_mate(self) -> bool:
        return self.mate_in is not None


@dataclass(frozen=True)
class AnalysisResult:
    """Engine ground truth for one position."""

    fen: str
    depth: int
    best: EngineLine
    top_moves: list[EngineLine]
    engine: str = "stockfish"

    @property
    def best_move(self) -> str:
        return self.best.move_san

    @property
    def eval_cp(self) -> int:
        return self.best.score_cp

    @property
    def pv(self) -> list[str]:
        return self.best.pv_san


@dataclass(frozen=True)
class MoveVerdict:
    """The engine's judgement of one played move. Never produced by an LLM."""

    fen: str
    played_move: str  # SAN
    best_move: str  # SAN
    best_move_uci: str  # the same move in UCI, so a board can draw it as an arrow
    best_line: list[str]  # SAN principal variation after the best move
    eval_cp_before: int  # from the mover's point of view
    eval_cp_after: int  # from the mover's point of view
    cp_loss: int
    win_prob_before: float  # 0..1 for the mover
    win_prob_after: float
    win_prob_loss: float
    label: str  # best | good | inaccuracy | mistake | blunder
    detected_motif: str | None = None
    taxonomy_keys: list[str] = field(default_factory=list)

    @property
    def is_mistake(self) -> bool:
        return self.label in ("inaccuracy", "mistake", "blunder")

    @property
    def is_serious(self) -> bool:
        return self.label in ("mistake", "blunder")


@dataclass(frozen=True)
class HumanMove:
    """A sparring move, plus which engine produced it so the UI can be honest."""

    move_san: str
    move_uci: str
    opponent_kind: str  # maia | stockfish-limited
    rating_band: int


class AnalysisEngine(Protocol):
    """Ground truth. Best move, evaluation, and the verdict on a played move."""

    def analyze(self, fen: str, depth: int | None = None, multipv: int | None = None) -> AnalysisResult: ...

    def classify_move(self, fen: str, played_move: str, depth: int | None = None) -> MoveVerdict: ...


class SparringEngine(Protocol):
    """A human-feeling opponent at a target rating."""

    def get_human_move(self, fen: str, rating_band: int) -> HumanMove: ...


# --------------------------------------------------------------------- scoring
def win_probability(cp: int) -> float:
    """Convert a centipawn score to a win probability in 0..1 for the side to move.

    Uses the logistic fit popularised by Lichess. Centipawn loss alone is unfair in
    decisive positions: dropping 200cp while up a queen barely changes the outcome,
    and labelling that a blunder teaches the wrong lesson.
    """
    clamped = max(-1500, min(1500, cp))
    return 1.0 / (1.0 + math.exp(-0.00368208 * clamped))


# Centipawn thresholds (Section 9). The upper bound of each label.
CP_THRESHOLDS: tuple[tuple[int, str], ...] = ((20, "good"), (50, "inaccuracy"), (150, "mistake"))
# Win-probability thresholds, in percentage points.
WP_THRESHOLDS: tuple[tuple[float, str], ...] = ((3.0, "good"), (7.0, "inaccuracy"), (15.0, "mistake"))

SEVERITY = {"best": 0, "good": 1, "inaccuracy": 2, "mistake": 3, "blunder": 4}
_SEVERITY = SEVERITY

# A forced mate that goes unplayed, or unnoticed against you, is decisive by definition.
# Win probability barely moves when you are already winning, so it would otherwise be
# labelled trivial -- exactly the moment a coach must not stay quiet.
MATE_FLOOR_LABEL = "mistake"


def at_least(label: str, floor: str) -> str:
    return label if SEVERITY[label] >= SEVERITY[floor] else floor


def _label_from(value: float, thresholds: tuple[tuple[float, str], ...]) -> str:
    for limit, name in thresholds:
        if value <= limit:
            return name
    return "blunder"


def classify_loss(cp_loss: int, win_prob_loss_pct: float, played_is_best: bool) -> str:
    """Label a move from both centipawn loss and win-probability loss.

    The milder of the two labels wins, which keeps judgement fair in already-decided
    positions while staying strict in sharp ones.
    """
    if played_is_best:
        return "best"
    cp_label = _label_from(cp_loss, CP_THRESHOLDS)
    wp_label = _label_from(win_prob_loss_pct, WP_THRESHOLDS)
    return cp_label if _SEVERITY[cp_label] <= _SEVERITY[wp_label] else wp_label
