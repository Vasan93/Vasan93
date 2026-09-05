#!/usr/bin/env python3
"""Import a subset of the open Lichess puzzle database (CC0).

    curl -O https://database.lichess.org/lichess_db_puzzle.csv.zst
    zstd -d lichess_db_puzzle.csv.zst
    python scripts/import_lichess_puzzles.py lichess_db_puzzle.csv --max-per-theme 400

The full file holds millions of puzzles, far more than a coaching app needs. This takes a
balanced sample across the weakness taxonomy, capped per theme and per rating band so the
assessment stays calibrated at every level.

CSV columns: PuzzleId,FEN,Moves,Rating,RatingDeviation,Popularity,NbPlays,Themes,GameUrl,OpeningTags
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.db import SessionLocal  # noqa: E402
from app.models import Puzzle  # noqa: E402
from app.weakness.taxonomy import TAXONOMY  # noqa: E402

# Lichess theme -> taxonomy key. One puzzle may train several weaknesses.
THEME_TO_KEY: dict[str, str] = {}
for entry in TAXONOMY.values():
    for theme in entry.puzzle_themes:
        THEME_TO_KEY.setdefault(theme, entry.key)

RATING_BANDS = ((0, 900), (900, 1200), (1200, 1500), (1500, 1800), (1800, 3000))


def band_of(rating: int) -> tuple[int, int]:
    for low, high in RATING_BANDS:
        if low <= rating < high:
            return low, high
    return RATING_BANDS[-1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--max-per-theme", type=int, default=300, help="cap per taxonomy key")
    parser.add_argument("--max-per-band", type=int, default=80, help="cap per key per rating band")
    parser.add_argument("--min-popularity", type=int, default=70)
    parser.add_argument("--min-plays", type=int, default=200)
    args = parser.parse_args()

    if not args.csv_path.exists():
        print(f"No such file: {args.csv_path}", file=sys.stderr)
        return 1

    per_key: dict[str, int] = defaultdict(int)
    per_key_band: dict[tuple[str, tuple[int, int]], int] = defaultdict(int)
    chosen: list[Puzzle] = []

    with open(args.csv_path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                rating = int(row["Rating"])
                popularity = int(row["Popularity"])
                plays = int(row["NbPlays"])
            except (KeyError, ValueError):
                continue
            if popularity < args.min_popularity or plays < args.min_plays:
                continue

            themes = row.get("Themes", "").split()
            keys = {THEME_TO_KEY[theme] for theme in themes if theme in THEME_TO_KEY}
            if not keys:
                continue

            band = band_of(rating)
            usable = [
                key
                for key in sorted(keys)
                if per_key[key] < args.max_per_theme and per_key_band[(key, band)] < args.max_per_band
            ]
            if not usable:
                continue
            for key in usable:
                per_key[key] += 1
                per_key_band[(key, band)] += 1

            chosen.append(
                Puzzle(
                    id=row["PuzzleId"],
                    fen=row["FEN"],
                    solution_moves=row["Moves"],
                    solution_san="",
                    themes=" ".join(themes),
                    taxonomy_keys=" ".join(usable),
                    rating=rating,
                    # Lichess puzzles have a single forced solution line by construction.
                    kind="tactical",
                    tolerance_cp=30,
                    popularity=popularity,
                    source="lichess",
                )
            )

    with SessionLocal() as db:
        existing = {row[0] for row in db.query(Puzzle.id).all()}
        added = 0
        for puzzle in chosen:
            if puzzle.id in existing:
                continue
            db.add(puzzle)
            added += 1
            if added % 500 == 0:
                db.commit()
        db.commit()

    print(f"Imported {added} puzzles ({len(chosen)} selected).")
    for key, count in sorted(per_key.items()):
        print(f"  {key:28} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
