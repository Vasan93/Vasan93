"""Rating estimation from puzzle results.

An Elo-style sequential update: each puzzle is an "opponent" whose rating is the puzzle's
difficulty. K falls as evidence accumulates, so the estimate converges quickly over a
short assessment and then moves steadily during ordinary training.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

START_RATING = 1000
MIN_RATING = 400
MAX_RATING = 2800

# Assessment length. Long enough to be stable, short enough that a beginner finishes it.
ASSESSMENT_LENGTH = 10


def expected_score(student: float, puzzle: float) -> float:
    return 1.0 / (1.0 + 10 ** ((puzzle - student) / 400.0))


def k_factor(attempts: int) -> float:
    """Large early so the first few answers move the estimate a long way."""
    if attempts < 3:
        return 120.0
    if attempts < 6:
        return 80.0
    if attempts < 12:
        return 56.0
    if attempts < 30:
        return 32.0
    return 20.0


def update(rating: float, puzzle_rating: float, correct: bool, attempts: int) -> int:
    expected = expected_score(rating, puzzle_rating)
    actual = 1.0 if correct else 0.0
    moved = rating + k_factor(attempts) * (actual - expected)
    return int(round(max(MIN_RATING, min(MAX_RATING, moved))))


@dataclass
class Estimate:
    rating: int
    confidence_interval: int  # +/- points
    answered: int
    correct: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.answered if self.answered else 0.0


def estimate_from(results: list[tuple[int, bool]], start: int = START_RATING) -> Estimate:
    """Run the sequential update over (puzzle_rating, correct) pairs."""
    rating = float(start)
    correct = 0
    for index, (puzzle_rating, was_correct) in enumerate(results):
        rating = float(update(rating, puzzle_rating, was_correct, index))
        correct += int(was_correct)

    answered = len(results)
    # Wide after one answer, tightening roughly with the square root of the sample.
    interval = int(round(350 / math.sqrt(answered))) if answered else 400
    return Estimate(rating=int(round(rating)), confidence_interval=interval, answered=answered, correct=correct)


def next_difficulty(rating: int, answered: int, last_correct: bool | None) -> int:
    """Where to aim the next puzzle.

    Straight after a correct answer, stretch upward; after a miss, step back so the
    learner is not buried. The steps shrink as the estimate settles.
    """
    if last_correct is None:
        return rating
    step = max(60, 220 - answered * 20)
    return max(MIN_RATING, min(MAX_RATING, rating + step if last_correct else rating - step))
