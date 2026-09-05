"""Process-exit cleanup for engine subprocesses.

`python-chess` runs each engine's event loop on a **non-daemon** thread. CPython joins
non-daemon threads *before* running `atexit` handlers, so an `atexit`-registered close
never runs and the process hangs for ever. Any command-line entry point that touches the
engine would simply never exit.

`threading._register_atexit` runs callbacks *before* that join. It is the same hook
`concurrent.futures` uses for its worker pools, so it is the right mechanism here, with a
plain `atexit` fallback if it ever disappears.
"""
from __future__ import annotations

import atexit
import threading
from collections.abc import Callable

from app.core.logging import get_logger

log = get_logger(__name__)

_closers: list[Callable[[], None]] = []
_lock = threading.Lock()
_hooked = False


def _run_closers() -> None:
    with _lock:
        closers = list(_closers)
        _closers.clear()
    for close in closers:
        try:
            close()
        except Exception as exc:  # never block shutdown on a cleanup failure
            log.warning("Engine cleanup failed: %s", exc)


def _install_hook() -> None:
    global _hooked
    if _hooked:
        return
    register = getattr(threading, "_register_atexit", None)
    if callable(register):
        register(_run_closers)
    else:  # pragma: no cover - only on interpreters without the private hook
        atexit.register(_run_closers)
    _hooked = True


def register_closer(close: Callable[[], None]) -> None:
    """Close this engine when the interpreter shuts down."""
    with _lock:
        _closers.append(close)
    _install_hook()


def close_all() -> None:
    """Close every registered engine now. Used by the API's shutdown handler."""
    _run_closers()
