"""Background jobs for long analyses.

A game review takes tens of seconds, which is far too long for a request. Jobs run on a
worker pool and publish progress through the shared cache, so any process serving the
API can report status.

This is deliberately the smallest thing that works. The interface (`submit`, `status`)
is what callers depend on, so replacing the pool with RQ or Celery later is a swap
inside this module.
"""
from __future__ import annotations

import threading
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.core.cache import get_cache
from app.core.logging import get_logger

log = get_logger(__name__)

JOB_TTL_SECONDS = 3 * 3600


class JobRunner:
    def __init__(self, max_workers: int = 2) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job")
        self._lock = threading.Lock()
        self._running: set[str] = set()

    # ------------------------------------------------------------- status
    @staticmethod
    def _key(job_id: str) -> str:
        return f"job:{job_id}"

    def status(self, job_id: str) -> dict[str, Any]:
        stored = get_cache().get_json(self._key(job_id))
        return stored or {"state": "unknown", "progress": 0, "total": 0}

    def _write(self, job_id: str, **fields: Any) -> None:
        current = self.status(job_id)
        current.update(fields)
        get_cache().set_json(self._key(job_id), current, ttl_seconds=JOB_TTL_SECONDS)

    def report_progress(self, job_id: str, progress: int, total: int) -> None:
        self._write(job_id, state="running", progress=progress, total=total)

    # ------------------------------------------------------------- submit
    def submit(self, job_id: str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> bool:
        """Queue a job. Returns False when the same job is already in flight."""
        with self._lock:
            if job_id in self._running:
                return False
            self._running.add(job_id)

        self._write(job_id, state="queued", progress=0, total=0, error=None)
        self._pool.submit(self._run, job_id, func, *args, **kwargs)
        return True

    def _run(self, job_id: str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        try:
            self._write(job_id, state="running")
            result = func(*args, job_id=job_id, **kwargs)
            self._write(job_id, state="done", result=result, error=None)
        except Exception as exc:
            log.error("Job %s failed: %s\n%s", job_id, exc, traceback.format_exc())
            self._write(job_id, state="failed", error=str(exc))
        finally:
            with self._lock:
                self._running.discard(job_id)

    def is_running(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._running

    def wait_for(self, job_id: str, timeout: float = 120.0) -> dict[str, Any]:
        """Block until a job finishes. For tests and synchronous callers only."""
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.status(job_id)
            if status.get("state") in ("done", "failed"):
                return status
            time.sleep(0.1)
        return {"state": "timeout", "error": f"Job {job_id} did not finish in {timeout}s"}

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


_runner: JobRunner | None = None
_runner_lock = threading.Lock()


def get_job_runner() -> JobRunner:
    global _runner
    with _runner_lock:
        if _runner is None:
            _runner = JobRunner()
    return _runner
