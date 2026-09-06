"""Application settings. Everything comes from the environment; see .env.example."""
from __future__ import annotations

import secrets
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

    # Auth. Left blank on purpose: an unset secret is generated per process at startup
    # rather than falling back to a value that is public in the repository. See
    # `resolved_jwt_secret`.
    jwt_secret: str = ""
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

    # Populated on demand by `resolved_jwt_secret`; never read from the environment.
    _ephemeral_secret: str | None = None

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


    def resolved_jwt_secret(self) -> str:
        """The signing key, generating an ephemeral one when none is configured.

        A shipped default signing key is an authentication bypass: anyone who reads the
        repository can forge a token for any user. Generating a random key instead means
        an unconfigured deployment is inconvenient (sessions end when the process
        restarts) rather than silently insecure.
        """
        configured = self.jwt_secret.strip()
        if configured and not configured.startswith("change-me"):
            return configured
        if self._ephemeral_secret is None:
            object.__setattr__(self, "_ephemeral_secret", secrets.token_hex(32))
        return str(self._ephemeral_secret)

    def warn_if_insecure(self) -> list[str]:
        """Configuration problems worth shouting about at startup."""
        problems: list[str] = []
        configured = self.jwt_secret.strip()
        if not configured or configured.startswith("change-me"):
            problems.append(
                "JWT_SECRET is not set, so a random one was generated for this process. "
                "Everyone is signed out whenever the server restarts. "
                "Set one with `openssl rand -hex 32` before deploying."
            )
        elif len(configured) < 32:
            problems.append("JWT_SECRET is shorter than 32 bytes; generate one with `openssl rand -hex 32`.")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
