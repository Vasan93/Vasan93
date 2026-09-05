"""Load the puzzle bank into the database.

The bundled `data/puzzles.seed.json` is a small curated set, every puzzle verified
against Stockfish by `scripts/build_seed_puzzles.py`. For a real deployment, import a
subset of the open Lichess puzzle database with `scripts/import_lichess_puzzles.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import REPO_ROOT
from app.core.logging import get_logger
from app.models import Puzzle
from app.weakness.taxonomy import TAXONOMY_KEYS

log = get_logger(__name__)

SEED_PATH = REPO_ROOT / "data" / "puzzles.seed.json"


def load_seed_file(path: Path | None = None) -> list[dict]:
    source = path or SEED_PATH
    if not source.exists():
        log.warning("No puzzle seed file at %s", source)
        return []
    with open(source, encoding="utf-8") as handle:
        return json.load(handle)


def seed_puzzles(db: Session, path: Path | None = None) -> int:
    """Insert any puzzles not already present. Safe to run repeatedly."""
    records = load_seed_file(path)
    existing = set(db.scalars(select(Puzzle.id)).all())
    added = 0

    for record in records:
        if record["id"] in existing:
            continue
        keys = [key for key in record.get("taxonomy_keys", "").split() if key in TAXONOMY_KEYS]
        if not keys:
            log.warning("Puzzle %s has no known taxonomy key; skipped.", record["id"])
            continue
        db.add(
            Puzzle(
                id=record["id"],
                fen=record["fen"],
                solution_moves=record["solution_moves"],
                solution_san=record.get("solution_san", ""),
                themes=record.get("themes", ""),
                taxonomy_keys=" ".join(keys),
                rating=int(record["rating"]),
                kind=record.get("kind", "tactical"),
                tolerance_cp=int(record.get("tolerance_cp", 30)),
                popularity=int(record.get("popularity", 0)),
                source=record.get("source", "curated"),
            )
        )
        added += 1

    db.commit()
    return added
