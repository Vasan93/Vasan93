"""Application settings. Everything comes from the environment; see .env.example."""
from __future__ import annotations

import shutil
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+psycopg://grandmaster:grandmaster@localhost:5432/grandmasterai"

    # Cache / queue
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    # Coaching brain
    anthropic_api_key: str | None = None
    coach_model: str = "claude-opus-5"

    # Engines
    stockfish_path: str | None = None
    lc0_path: str | None = None
    maia_weights_dir: str = "engines/weights"

    # App
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def resolved_stockfish_path(self) -> str | None:
        if self.stockfish_path and Path(self.stockfish_path).exists():
            return self.stockfish_path
        for candidate in ("/usr/games/stockfish", "/usr/bin/stockfish", "/usr/local/bin/stockfish"):
            if Path(candidate).exists():
                return candidate
        return shutil.which("stockfish")

    def resolved_lc0_path(self) -> str | None:
        if self.lc0_path and Path(self.lc0_path).exists():
            return self.lc0_path
        return shutil.which("lc0")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
