"""Cache used for engine results and rate limiting.

Redis when it is available; otherwise an in-process store with the same expiry
semantics. Expiry is not optional in the fallback: rate-limit counters that never
reset would lock users out of a single-process deployment permanently.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any

from app.core.config import settings


class _MemoryStore:
    """Minimal expiring key/value store."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float | None]] = {}
        self._lock = threading.Lock()

    def _live(self, key: str) -> str | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and expires_at <= time.monotonic():
            self._data.pop(key, None)
            return None
        return value

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._live(key)

    def set(self, key: str, value: str, ttl_seconds: int | None) -> None:
        with self._lock:
            self._data[key] = (value, time.monotonic() + ttl_seconds if ttl_seconds else None)

    def incr(self, key: str, ttl_seconds: int) -> int:
        with self._lock:
            current = self._live(key)
            count = int(current) + 1 if current is not None else 1
            # Keep the original window: only a fresh counter sets the expiry.
            expires_at = self._data[key][1] if current is not None else time.monotonic() + ttl_seconds
            self._data[key] = (str(count), expires_at)
            return count

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class Cache:
    def __init__(self, url: str | None = None) -> None:
        self._memory = _MemoryStore()
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
            self._memory.set(key, raw, ttl_seconds)

    def incr_with_ttl(self, key: str, ttl_seconds: int) -> int:
        """Increment a counter that expires. Used for rate limiting."""
        if self._client:
            pipe = self._client.pipeline()
            pipe.incr(key)
            pipe.expire(key, ttl_seconds, nx=True)
            return int(pipe.execute()[0])
        return self._memory.incr(key, ttl_seconds)

    def clear(self) -> None:
        """Drop everything. Used by tests and by local development resets."""
        if self._client:
            self._client.flushdb()
        self._memory.clear()


_cache: Cache | None = None


def get_cache() -> Cache:
    global _cache
    if _cache is None:
        _cache = Cache()
    return _cache
