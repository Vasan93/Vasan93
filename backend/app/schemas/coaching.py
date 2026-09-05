"""Coaching payloads."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ExplainRequest(BaseModel):
    game_id: int
    ply: int = Field(ge=1)


class CoachingText(BaseModel):
    text: str
    source: str  # claude | template
    language: str  # the language the text is written in
    requested_language: str  # the language the learner asked for
    language_fallback: bool = False
    notes: list[str] = []


class LessonRequest(BaseModel):
    taxonomy_key: str = Field(max_length=48)


class LessonSection(BaseModel):
    heading: str
    body: str


class LessonExample(BaseModel):
    fen: str
    move: str
    explanation: str
    from_your_game: bool = False


class LessonCheck(BaseModel):
    fen: str
    question: str
    hint: str = ""
    # The answer is deliberately withheld until the student has attempted it.


class LessonOut(BaseModel):
    id: int
    topic: str
    topic_label: str
    title: str
    language: str
    intro: str
    source: str
    opening: str
    sections: list[LessonSection]
    examples: list[LessonExample]
    check: LessonCheck | None
    passed: bool | None = None
    score: float | None = None


class CheckAnswer(BaseModel):
    answer: str = Field(max_length=12)


class CheckResult(BaseModel):
    correct: bool
    best_move: str
    cp_loss: int
    feedback: str
    source: str
    language_fallback: bool = False


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2_000)
