"""Persistence for the weakness profile.

The scoring lives in `app.weakness.model` and stays pure; this module only reads and
writes it.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Weakness
from app.weakness.model import (
    Evidence,
    WeaknessScore,
    aggregate,
    record_failure,
    record_success,
    top_weaknesses,
)


def load_profile(db: Session, user_id: int) -> dict[str, WeaknessScore]:
    rows = db.scalars(select(Weakness).where(Weakness.user_id == user_id)).all()
    return {
        row.taxonomy_key: WeaknessScore(
            taxonomy_key=row.taxonomy_key,
            evidence_count=row.evidence_count,
            evidence_weight=row.evidence_weight,
            success_count=row.success_count,
            confidence=row.confidence_score,
            status=row.status,
        )
        for row in rows
    }


def save_profile(db: Session, user_id: int, scores: dict[str, WeaknessScore]) -> None:
    existing = {row.taxonomy_key: row for row in db.scalars(select(Weakness).where(Weakness.user_id == user_id)).all()}
    for key, score in scores.items():
        row = existing.get(key)
        if row is None:
            row = Weakness(user_id=user_id, taxonomy_key=key)
            db.add(row)
        row.confidence_score = score.confidence
        row.evidence_count = score.evidence_count
        row.success_count = score.success_count
        row.status = score.status
        row.evidence_weight = score.evidence_weight
    db.flush()


def apply_evidence(db: Session, user_id: int, evidence: list[Evidence]) -> dict[str, WeaknessScore]:
    profile = load_profile(db, user_id)
    updated = aggregate(evidence, prior=profile)
    save_profile(db, user_id, updated)
    return updated


def record_attempt_result(db: Session, user_id: int, taxonomy_key: str, correct: bool) -> WeaknessScore | None:
    """Fold a puzzle or quiz result into the profile."""
    profile = load_profile(db, user_id)
    score = profile.get(taxonomy_key)
    if score is None:
        if correct:
            return None  # nothing to improve on a weakness we never saw
        score = WeaknessScore(taxonomy_key=taxonomy_key)
        profile[taxonomy_key] = score
    record_success(score) if correct else record_failure(score)
    save_profile(db, user_id, profile)
    return score


def profile_summary(db: Session, user_id: int, limit: int = 3) -> list[WeaknessScore]:
    return top_weaknesses(load_profile(db, user_id), limit=limit)
