"""SQLAlchemy models.

The full Section 8 data model is declared up front so foreign keys and enums stay
consistent; each phase populates the tables it needs.
"""
from app.models.game import AnalyzedMove, Game
from app.models.learning import CoachingLog, Lesson, PuzzleAttempt, SrsCard, Weakness
from app.models.puzzle import Puzzle
from app.models.user import RatingHistory, User

__all__ = [
    "AnalyzedMove",
    "CoachingLog",
    "Game",
    "Lesson",
    "Puzzle",
    "PuzzleAttempt",
    "RatingHistory",
    "SrsCard",
    "User",
    "Weakness",
]
