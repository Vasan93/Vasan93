"""Engine request/response payloads."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.engines.base import AnalysisResult, MoveVerdict


class AnalyzeRequest(BaseModel):
    fen: str = Field(max_length=120)
    depth: int | None = Field(default=None, ge=6, le=24)
    multipv: int | None = Field(default=None, ge=1, le=5)


class ClassifyRequest(BaseModel):
    fen: str = Field(max_length=120)
    move: str = Field(max_length=12)
    depth: int | None = Field(default=None, ge=6, le=24)


class LineOut(BaseModel):
    move_san: str
    move_uci: str
    score_cp: int
    mate_in: int | None
    pv_san: list[str]


class AnalysisOut(BaseModel):
    fen: str
    depth: int
    best_move: str
    eval_cp: int
    mate_in: int | None
    top_moves: list[LineOut]
    engine: str

    @classmethod
    def from_result(cls, result: AnalysisResult) -> "AnalysisOut":
        return cls(
            fen=result.fen,
            depth=result.depth,
            best_move=result.best.move_san,
            eval_cp=result.best.score_cp,
            mate_in=result.best.mate_in,
            top_moves=[
                LineOut(
                    move_san=line.move_san,
                    move_uci=line.move_uci,
                    score_cp=line.score_cp,
                    mate_in=line.mate_in,
                    pv_san=line.pv_san,
                )
                for line in result.top_moves
            ],
            engine=result.engine,
        )


class VerdictOut(BaseModel):
    fen: str
    played_move: str
    best_move: str
    best_move_uci: str
    best_line: list[str]
    eval_cp_before: int
    eval_cp_after: int
    cp_loss: int
    win_prob_before: float
    win_prob_after: float
    win_prob_loss: float
    label: str
    detected_motif: str | None
    taxonomy_keys: list[str]
    taxonomy_labels: list[str]

    @classmethod
    def from_verdict(cls, verdict: MoveVerdict) -> "VerdictOut":
        from app.weakness.taxonomy import label as taxonomy_label

        return cls(
            **{field: getattr(verdict, field) for field in (
                "fen", "played_move", "best_move", "best_move_uci", "best_line", "eval_cp_before", "eval_cp_after",
                "cp_loss", "win_prob_before", "win_prob_after", "win_prob_loss", "label",
                "detected_motif", "taxonomy_keys",
            )},
            taxonomy_labels=[taxonomy_label(key) for key in verdict.taxonomy_keys],
        )


class SparringInfo(BaseModel):
    opponent_kind: str
    maia_available: bool
    lc0_path: str | None
    maia_bands: list[int]
    note: str
