"""Spaced repetition over weaknesses, SM-2 style.

One card per active weakness. A weakness is not "fixed" because the learner solved one
puzzle: it is fixed when they keep solving that pattern at growing intervals. The
scheduler is pure so the retirement rules can be tested without a database.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# SM-2 constants, lightly tuned: chess patterns are re-encountered in real games, so the
# first two intervals are shorter than in vocabulary decks.
MIN_EASE = 1.3
DEFAULT_EASE = 2.5
FIRST_INTERVAL_DAYS = 1.0
SECOND_INTERVAL_DAYS = 3.0

# Successes needed at growing intervals before a weakness may retire.
SUCCESSES_TO_RETIRE = 3


@dataclass
class CardState:
    ease: float = DEFAULT_EASE
    interval_days: float = 0.0
    repetitions: int = 0
    successes: int = 0
    lapses: int = 0
    due_at: datetime | None = None

    @property
    def ready_to_retire(self) -> bool:
        return self.successes >= SUCCESSES_TO_RETIRE and self.interval_days >= 7.0


def _quality(correct: bool, seconds: float | None) -> int:
    """Map an attempt to an SM-2 grade of 0-5.

    Speed matters: solving a pattern instantly is different from grinding it out, and
    "moving too fast" is itself a tracked weakness.
    """
    if not correct:
        return 2 if seconds is not None and seconds > 30 else 1
    if seconds is None:
        return 4
    if seconds <= 10:
        return 5
    if seconds <= 45:
        return 4
    return 3


def review(state: CardState, correct: bool, seconds: float | None = None, now: datetime | None = None) -> CardState:
    """Apply one attempt and return the updated card."""
    now = now or datetime.now(timezone.utc)
    quality = _quality(correct, seconds)

    if quality < 3:
        # A miss resets the interval. The pattern is not learned yet.
        updated = CardState(
            ease=max(MIN_EASE, state.ease - 0.2),
            interval_days=FIRST_INTERVAL_DAYS,
            repetitions=0,
            successes=max(0, state.successes - 1),
            lapses=state.lapses + 1,
        )
    else:
        repetitions = state.repetitions + 1
        if repetitions == 1:
            interval = FIRST_INTERVAL_DAYS
        elif repetitions == 2:
            interval = SECOND_INTERVAL_DAYS
        else:
            interval = state.interval_days * state.ease
        ease = state.ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        updated = CardState(
            ease=max(MIN_EASE, round(ease, 3)),
            interval_days=round(min(interval, 180.0), 2),
            repetitions=repetitions,
            successes=state.successes + 1,
            lapses=state.lapses,
        )

    updated.due_at = now + timedelta(days=updated.interval_days)
    return updated


def is_due(state: CardState, now: datetime | None = None) -> bool:
    if state.due_at is None:
        return True
    now = now or datetime.now(timezone.utc)
    due = state.due_at if state.due_at.tzinfo else state.due_at.replace(tzinfo=timezone.utc)
    return due <= now
