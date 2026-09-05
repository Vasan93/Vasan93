"""The weakness model: pure, testable logic. No engine calls, no LLM calls.

It consumes labelled mistakes and emits a confidence score per taxonomy key. The point
is to distinguish a *pattern* from a bad day: one blunder is noise, the same motif three
times across two games is a weakness worth teaching.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.weakness.taxonomy import TAXONOMY_KEYS

# How much each label counts as evidence.
SEVERITY_WEIGHT: dict[str, float] = {"inaccuracy": 0.4, "mistake": 1.0, "blunder": 1.6}

# Evidence needed before we are reasonably sure. At this much weight, confidence is ~0.63.
CONFIDENCE_SCALE = 3.0

# Each spaced success cancels this much evidence.
SUCCESS_WEIGHT = 1.0

# Status thresholds.
IMPROVING_SUCCESSES = 2
RETIRE_SUCCESSES = 3
RETIRE_CONFIDENCE = 0.25

# A weakness seen in only a handful of chances is not yet a pattern.
MIN_EVIDENCE_FOR_ACTIVE = 1


@dataclass(frozen=True)
class Evidence:
    """One mistake, already labelled by the engine."""

    taxonomy_key: str
    label: str  # inaccuracy | mistake | blunder
    game_id: int | None = None
    ply: int | None = None

    @property
    def weight(self) -> float:
        return SEVERITY_WEIGHT.get(self.label, 0.0)


@dataclass
class WeaknessScore:
    taxonomy_key: str
    evidence_count: int = 0
    evidence_weight: float = 0.0
    success_count: int = 0
    confidence: float = 0.0
    status: str = "active"
    examples: list[tuple[int | None, int | None]] = field(default_factory=list)  # (game_id, ply)


def confidence_from(evidence_weight: float, success_count: int = 0) -> float:
    """Map accumulated evidence to a 0..1 confidence.

    Saturating rather than linear: the tenth blunder of the same kind should not make us
    ten times as certain as the first, and successes pull the score back down.
    """
    net = max(0.0, evidence_weight - success_count * SUCCESS_WEIGHT)
    return round(1.0 - math.exp(-net / CONFIDENCE_SCALE), 4)


def status_for(confidence: float, success_count: int) -> str:
    """active -> improving. Retirement is decided elsewhere.

    Counting successes is not enough to call a pattern fixed: they have to be spread
    over growing intervals, and only the spaced-repetition card knows that. So this
    function never returns "retired" -- `app.curriculum.service` does that when the card
    says the learner has held the pattern over time.
    """
    if success_count >= IMPROVING_SUCCESSES:
        return "improving"
    return "active"


def eligible_to_retire(score: "WeaknessScore") -> bool:
    """Whether confidence has fallen far enough for retirement to be honest."""
    return score.success_count >= RETIRE_SUCCESSES and score.confidence <= RETIRE_CONFIDENCE


def aggregate(
    evidence: list[Evidence],
    prior: dict[str, WeaknessScore] | None = None,
) -> dict[str, WeaknessScore]:
    """Fold new evidence into an existing profile and rescore every touched key."""
    scores: dict[str, WeaknessScore] = {
        key: WeaknessScore(
            taxonomy_key=score.taxonomy_key,
            evidence_count=score.evidence_count,
            evidence_weight=score.evidence_weight,
            success_count=score.success_count,
            confidence=score.confidence,
            status=score.status,
            examples=list(score.examples),
        )
        for key, score in (prior or {}).items()
    }

    for item in evidence:
        if item.taxonomy_key not in TAXONOMY_KEYS:
            continue  # detection must never invent keys
        if item.weight == 0.0:
            continue
        score = scores.setdefault(item.taxonomy_key, WeaknessScore(taxonomy_key=item.taxonomy_key))
        score.evidence_count += 1
        score.evidence_weight += item.weight
        if len(score.examples) < 8:
            score.examples.append((item.game_id, item.ply))

    for score in scores.values():
        score.confidence = confidence_from(score.evidence_weight, score.success_count)
        if score.status != "retired":
            score.status = status_for(score.confidence, score.success_count)
    return scores


def record_success(score: WeaknessScore) -> WeaknessScore:
    """A spaced success against this weakness. Lowers confidence."""
    score.success_count += 1
    score.confidence = confidence_from(score.evidence_weight, score.success_count)
    if score.status != "retired":
        score.status = status_for(score.confidence, score.success_count)
    return score


def record_failure(score: WeaknessScore) -> WeaknessScore:
    """A failed attempt. Adds evidence and reopens a weakness, retired or not."""
    score.evidence_count += 1
    score.evidence_weight += SEVERITY_WEIGHT["mistake"]
    score.success_count = max(0, score.success_count - 1)
    score.confidence = confidence_from(score.evidence_weight, score.success_count)
    score.status = status_for(score.confidence, score.success_count)
    return score


def top_weaknesses(scores: dict[str, WeaknessScore], limit: int = 3, include_improving: bool = False) -> list[WeaknessScore]:
    """The weaknesses worth teaching next, most confident first."""
    allowed = {"active", "improving"} if include_improving else {"active"}
    ranked = [
        score
        for score in scores.values()
        if score.status in allowed and score.evidence_count >= MIN_EVIDENCE_FOR_ACTIVE
    ]
    ranked.sort(key=lambda score: (-score.confidence, -score.evidence_weight, score.taxonomy_key))
    return ranked[:limit]
