"""GrandmasterAI backend entrypoint."""
from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    assessment,
    auth,
    coach,
    dashboard,
    engine,
    games,
    health,
    practice,
    puzzles,
    review,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.engines.lifecycle import close_all

log = get_logger(__name__)

app = FastAPI(
    title="GrandmasterAI",
    description="A standalone AI chess coach: engine truth, human teaching.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Slow requests are the ones worth noticing: engine analysis and coaching calls.
SLOW_REQUEST_MS = 2_000


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Time every request and give failures a traceable id."""
    request_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed = (time.perf_counter() - started) * 1000
        log.exception("request %s %s %s failed after %.0fms", request_id, request.method, request.url.path, elapsed)
        return JSONResponse(
            status_code=500,
            content={"detail": "Something went wrong on our side.", "request_id": request_id},
        )

    elapsed = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    if elapsed >= SLOW_REQUEST_MS or response.status_code >= 500:
        log.warning(
            "slow request %s %s %s -> %d in %.0fms",
            request_id, request.method, request.url.path, response.status_code, elapsed,
        )
    return response


app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(assessment.router, prefix="/api")
app.include_router(engine.router, prefix="/api")
app.include_router(games.router, prefix="/api")
app.include_router(review.router, prefix="/api")
app.include_router(coach.router, prefix="/api")
app.include_router(puzzles.router, prefix="/api")
app.include_router(practice.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")


@app.on_event("startup")
def on_startup() -> None:
    log.info("GrandmasterAI starting. stockfish=%s lc0=%s", settings.resolved_stockfish_path(), settings.resolved_lc0_path())
    for problem in settings.warn_if_insecure():
        log.warning("SECURITY: %s", problem)


@app.on_event("shutdown")
def on_shutdown() -> None:
    close_all()
    log.info("Engines closed.")
