"""Weakness profile and review payloads."""
from __future__ import annotations

from pydantic import BaseModel

from app.weakness.model import WeaknessScore
from app.weakness.taxonomy import TAXONOMY


class WeaknessOut(BaseModel):
    taxonomy_key: str
    label: str
    category: str
    description: str
    teaching_topic: str
    confidence: float
    evidence_count: int
    success_count: int
    status: str

    @classmethod
    def from_score(cls, score: WeaknessScore) -> "WeaknessOut":
        entry = TAXONOMY[score.taxonomy_key]
        return cls(
            taxonomy_key=score.taxonomy_key,
            label=entry.label,
            category=str(entry.category),
            description=entry.description,
            teaching_topic=entry.teaching_topic,
            confidence=score.confidence,
            evidence_count=score.evidence_count,
            success_count=score.success_count,
            status=score.status,
        )


class ReviewedMoveOut(BaseModel):
    ply: int
    move_number: int
    side: str
    fen: str
    played_move: str
    best_move: str
    best_move_uci: str
    best_line: list[str]
    eval_cp_before: int
    eval_cp_after: int
    cp_loss: int
    win_prob_loss: float
    move_label: str
    detected_motif: str | None
    taxonomy_keys: list[str]
    taxonomy_labels: list[str]


class ReviewStatus(BaseModel):
    game_id: int
    state: str  # pending | queued | running | done | failed
    progress: int = 0
    total: int = 0
    accuracy: float | None = None
    label_counts: dict[str, int] = {}
    error: str | None = None
    moves: list[ReviewedMoveOut] = []
