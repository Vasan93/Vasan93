"""Create tables and (optionally) seed reference data.

Run: `python -m app.bootstrap [--seed]` from the backend directory.

Alembic owns schema migrations; this entrypoint exists so a fresh checkout or a
container start comes up with a usable database in one command.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import text

from app import models  # noqa: F401  (registers mappers before create_all)
from app.core.db import Base, SessionLocal, engine
from app.core.logging import get_logger

log = get_logger(__name__)


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)
    log.info("Schema ready (%d tables).", len(Base.metadata.tables))


def wait_for_db(attempts: int = 30, delay: float = 1.0) -> bool:
    import time

    for attempt in range(1, attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            if attempt == attempts:
                log.error("Database unreachable after %d attempts: %s", attempts, exc)
                return False
            time.sleep(delay)
    return False


def seed() -> None:
    """Load the puzzle bank. Safe to run repeatedly."""
    from app.curriculum.seed import seed_puzzles

    with SessionLocal() as db:
        added = seed_puzzles(db)
    log.info("Seeded %d new puzzles.", added)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the GrandmasterAI database.")
    parser.add_argument("--seed", action="store_true", help="also load the puzzle bank")
    args = parser.parse_args()

    if not wait_for_db():
        return 1
    create_tables()
    if args.seed:
        seed()
    return 0


if __name__ == "__main__":
    sys.exit(main())
