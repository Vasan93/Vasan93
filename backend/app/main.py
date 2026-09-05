"""GrandmasterAI backend entrypoint."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, engine, games, health, review
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

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(engine.router, prefix="/api")
app.include_router(games.router, prefix="/api")
app.include_router(review.router, prefix="/api")


@app.on_event("startup")
def on_startup() -> None:
    log.info("GrandmasterAI starting. stockfish=%s lc0=%s", settings.resolved_stockfish_path(), settings.resolved_lc0_path())
    for problem in settings.warn_if_insecure():
        log.warning("SECURITY: %s", problem)


@app.on_event("shutdown")
def on_shutdown() -> None:
    close_all()
    log.info("Engines closed.")
