"""Shared FastAPI dependencies: current user, rate limiting."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.cache import get_cache
from app.core.db import get_db
from app.core.security import decode_access_token
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    subject = decode_access_token(credentials.credentials)
    if subject is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, int(subject)) if subject.isdigit() else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    return user


class RateLimit:
    """Fixed-window rate limit keyed by client address and route.

    Engine analysis and LLM calls are expensive, so the routes that trigger them
    carry a limit.
    """

    def __init__(self, limit: int, window_seconds: int, name: str) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.name = name

    def __call__(self, request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        auth = request.headers.get("authorization", "")
        identity = auth[-24:] if auth else client
        key = f"ratelimit:{self.name}:{identity}"
        count = get_cache().incr_with_ttl(key, self.window_seconds)
        if count > self.limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Too many requests. Limit is {self.limit} per {self.window_seconds}s for this action.",
            )
