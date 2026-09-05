"""Redis-backed cache with an in-memory fallback so the app runs without Redis."""
from __future__ import annotations

import json
import threading
from typing import Any

from app.core.config import settings


class Cache:
    """Small key/value cache used for engine analysis results and rate limiting."""

    def __init__(self, url: str | None = None) -> None:
        self._memory: dict[str, str] = {}
        self._lock = threading.Lock()
        self._client: Any = None
        try:
            import redis  # imported lazily so the dependency stays optional

            client = redis.Redis.from_url(url or settings.redis_url, decode_responses=True, socket_connect_timeout=1)
            client.ping()
            self._client = client
        except Exception:
            self._client = None

    @property
    def backend(self) -> str:
        return "redis" if self._client is not None else "memory"

    @property
    def available(self) -> bool:
        return self._client is not None

    def get_json(self, key: str) -> Any | None:
        raw = self._client.get(key) if self._client else self._memory.get(key)
        return json.loads(raw) if raw else None

    def set_json(self, key: str, value: Any, ttl_seconds: int = 86_400) -> None:
        raw = json.dumps(value)
        if self._client:
            self._client.set(key, raw, ex=ttl_seconds)
        else:
            with self._lock:
                self._memory[key] = raw

    def incr_with_ttl(self, key: str, ttl_seconds: int) -> int:
        """Increment a counter that expires. Used for rate limiting."""
        if self._client:
            pipe = self._client.pipeline()
            pipe.incr(key)
            pipe.expire(key, ttl_seconds, nx=True)
            return int(pipe.execute()[0])
        with self._lock:
            current = int(self._memory.get(key, "0")) + 1
            self._memory[key] = str(current)
            return current


_cache: Cache | None = None


def get_cache() -> Cache:
    global _cache
    if _cache is None:
        _cache = Cache()
    return _cache
