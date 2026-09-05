"""Health endpoint. Reports the status of every external dependency."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.cache import get_cache
from app.core.config import settings
from app.core.db import get_db

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:  # pragma: no cover - depends on the environment
        database = f"error: {type(exc).__name__}"

    cache = get_cache()
    stockfish = settings.resolved_stockfish_path()
    lc0 = settings.resolved_lc0_path()

    components = {
        "database": database,
        "cache": cache.backend,
        "stockfish": stockfish or "missing",
        "lc0": lc0 or "missing (Maia sparring disabled)",
        "coaching_brain": "claude" if settings.anthropic_api_key else "template-fallback",
    }
    healthy = database == "ok" and stockfish is not None
    return {"status": "ok" if healthy else "degraded", "service": "GrandmasterAI", "components": components}
