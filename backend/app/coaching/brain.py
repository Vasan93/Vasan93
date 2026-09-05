"""The coaching brain: the layer that turns engine truth into human teaching.

A chess engine is a brilliant player and a terrible teacher. Everything that makes this
product worth using lives here: explanation, personalisation, language and warmth.

Two rules hold throughout:
  1. The brain is *given* every evaluation. It never produces one.
  2. Correctness is verified elsewhere (see `app.coaching.validation`). The brain only
     supplies language.

The provider sits behind `CoachingBrain`, so swapping models or vendors is one class.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.config import settings
from app.core.logging import get_logger
from app.coaching.prompts import v1

log = get_logger(__name__)

# Short, warm answers. Coaching prose is not a long-form task.
EXPLANATION_MAX_TOKENS = 1_000
LESSON_MAX_TOKENS = 4_000
CHAT_MAX_TOKENS = 1_200


@dataclass
class CoachingResponse:
    text: str
    source: str  # claude | template
    model: str = ""
    # The language the text is actually written in.
    language: str = "English"
    # The language the learner asked for. These differ only in the fallback.
    requested_language: str = "English"
    prompt_version: str = v1.VERSION
    system_prompt: str = ""
    user_prompt: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    structured: dict[str, Any] | None = None
    # True when the text could not be written in the learner's language.
    language_fallback: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class LearnerContext:
    """Everything the brain is allowed to know about the student."""

    name: str = "there"
    language: str = "English"
    rating: int = 1000
    goal: str = ""
    weaknesses: list[str] = field(default_factory=list)

    @property
    def level(self) -> str:
        if self.rating < 900:
            return "beginner"
        if self.rating < 1400:
            return "improving club"
        if self.rating < 1800:
            return "intermediate"
        return "advanced"

    @property
    def weakness_text(self) -> str:
        return ", ".join(self.weaknesses) if self.weaknesses else ""


class CoachingBrain(Protocol):
    """Stateless per call. Receives structured context, returns language."""

    source: str

    def explain_mistake(self, learner: LearnerContext, facts: dict[str, Any]) -> CoachingResponse: ...

    def build_lesson(self, learner: LearnerContext, topic: str, reason: str) -> CoachingResponse: ...

    def check_feedback(self, learner: LearnerContext, facts: dict[str, Any]) -> CoachingResponse: ...

    def assessment_summary(self, learner: LearnerContext, facts: dict[str, Any]) -> CoachingResponse: ...

    def chat(self, learner: LearnerContext, question: str, history: list[dict[str, str]]) -> CoachingResponse: ...


# --------------------------------------------------------------------- Claude
class ClaudeBrain:
    """Claude-backed coach."""

    source = "claude"

    def __init__(self, client: Any | None = None, model: str | None = None) -> None:
        self.model = model or settings.coach_model
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        return self._client

    # ------------------------------------------------------------- plumbing
    def _call(
        self,
        system: str,
        prompt: str,
        max_tokens: int,
        language: str,
        *,
        schema: dict | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> CoachingResponse:
        started = time.monotonic()
        messages: list[dict[str, Any]] = [*(history or []), {"role": "user", "content": prompt}]

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "thinking": {"type": "adaptive"},
            # Coaching prose is a short task; low effort keeps it fast and cheap.
            "output_config": {"effort": "low"},
            # A policy decline would otherwise leave the student with nothing.
            "betas": ["server-side-fallback-2026-07-01"],
            "fallbacks": "default",
        }
        if schema is not None:
            kwargs["output_config"] = {"effort": "medium", "format": {"type": "json_schema", "schema": schema}}

        response = self.client.beta.messages.create(**kwargs)
        latency_ms = int((time.monotonic() - started) * 1000)

        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            raise BrainRefusal(f"The coach declined to answer ({getattr(details, 'category', 'unknown')}).")

        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        usage = getattr(response, "usage", None)

        structured: dict[str, Any] | None = None
        if schema is not None:
            try:
                structured = json.loads(text)
            except json.JSONDecodeError as exc:
                raise BrainError(f"The coach returned malformed lesson data: {exc}") from exc

        return CoachingResponse(
            text=text.strip(),
            source=self.source,
            model=getattr(response, "model", self.model),
            language=language,
            requested_language=language,
            system_prompt=system,
            user_prompt=prompt,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            latency_ms=latency_ms,
            structured=structured,
        )

    def _persona(self, learner: LearnerContext) -> str:
        return v1.persona(learner.level, learner.language, learner.name, learner.goal)

    # -------------------------------------------------------------- surface
    def explain_mistake(self, learner: LearnerContext, facts: dict[str, Any]) -> CoachingResponse:
        prompt = v1.mistake_explanation(
            fen=facts["fen"],
            played_move=facts["played_move"],
            best_move=facts["best_move"],
            cp_loss=facts["cp_loss"],
            eval_before=facts["eval_cp_before"],
            eval_after=facts["eval_cp_after"],
            best_line=" ".join(facts.get("best_line", [])),
            motif=facts.get("detected_motif") or "",
            weaknesses=learner.weakness_text,
            phase=facts.get("phase", "middlegame"),
            name=learner.name,
        )
        return self._call(self._persona(learner), prompt, EXPLANATION_MAX_TOKENS, learner.language)

    def build_lesson(self, learner: LearnerContext, topic: str, reason: str) -> CoachingResponse:
        prompt = v1.lesson(topic, reason, learner.rating, learner.weakness_text, learner.language)
        return self._call(
            self._persona(learner), prompt, LESSON_MAX_TOKENS, learner.language, schema=v1.LESSON_SCHEMA
        )

    def check_feedback(self, learner: LearnerContext, facts: dict[str, Any]) -> CoachingResponse:
        prompt = v1.check_feedback(
            fen=facts["fen"],
            question=facts.get("question", ""),
            answer=facts["answer"],
            student_answer=facts["student_answer"],
            correct=facts["correct"],
            engine_note=facts.get("engine_note", ""),
        )
        return self._call(self._persona(learner), prompt, EXPLANATION_MAX_TOKENS, learner.language)

    def assessment_summary(self, learner: LearnerContext, facts: dict[str, Any]) -> CoachingResponse:
        prompt = v1.assessment_summary(
            rating=facts["rating"],
            area_summary=facts.get("area_summary", ""),
            weaknesses=learner.weakness_text,
            games_reviewed=facts.get("games_reviewed", 0),
            goal=learner.goal,
        )
        return self._call(self._persona(learner), prompt, EXPLANATION_MAX_TOKENS, learner.language)

    def chat(self, learner: LearnerContext, question: str, history: list[dict[str, str]]) -> CoachingResponse:
        system = self._persona(learner) + "\n\n" + v1.chat_context(
            learner.rating, learner.weakness_text, facts_topics(history), learner.language
        )
        return self._call(system, question, CHAT_MAX_TOKENS, learner.language, history=history)


def facts_topics(history: list[dict[str, str]]) -> str:
    return ", ".join(item.get("topic", "") for item in history if item.get("topic"))[:200]


class BrainError(RuntimeError):
    """The coaching brain could not produce usable text."""


class BrainRefusal(BrainError):
    """The model declined to answer."""


# ------------------------------------------------------------------ fallback
class TemplateBrain:
    """Engine-grounded coaching without an LLM.

    Every fact here comes from the engine, so this is correct but plain: no
    personalisation, no warmth to speak of, and English only. It exists so the product
    runs end to end without an API key, and it is honest about what it is: responses
    carry `language_fallback` when the learner asked for another language.
    """

    source = "template"

    def _wrap(self, text: str, learner: LearnerContext, kind: str) -> CoachingResponse:
        return CoachingResponse(
            text=text,
            source=self.source,
            model="",
            language="English",
            requested_language=learner.language,
            system_prompt=f"[template:{kind}]",
            user_prompt="",
            language_fallback=learner.language.lower() != "english",
            notes=["Generated from a template because no coaching model is configured."],
        )

    def explain_mistake(self, learner: LearnerContext, facts: dict[str, Any]) -> CoachingResponse:
        played = facts["played_move"]
        best = facts["best_move"]
        motif = (facts.get("detected_motif") or "").replace("_", " ")
        pawns = abs(facts["cp_loss"]) / 100

        if facts["eval_cp_before"] > 9000 and facts["eval_cp_after"] < 9000:
            headline = f"After {played} the forced mate slipped away. {best} finished the game."
        elif facts["eval_cp_after"] < -9000:
            headline = f"{played} walks into a forced mate. {best} held the position together."
        else:
            headline = f"{played} gave away about {pawns:.1f} pawns of advantage. The engine prefers {best}."

        lesson = {
            "hung piece": "Before you move, check every piece you own: is it defended, and does this move leave it loose?",
            "missed capture": "Scan for undefended enemy pieces every single move. Free material is the cheapest advantage there is.",
            "missed fork": "Look for one move that attacks two things at once, especially with a knight.",
            "missed mate": "When the enemy king has few escape squares, count checks before anything else.",
            "missed pin": "Look for enemy pieces standing on the same line as their king or queen.",
            "missed skewer": "When two valuable pieces line up, check whether attacking the front one wins the back one.",
            "early queen": "Develop knights and bishops before bringing the queen out; an early queen just gets chased.",
            "castling delayed": "Castle early. A king in the centre is the most common reason beginners lose quickly.",
            "threat ignored": "After the opponent moves, ask what it threatens before you continue your own plan.",
        }.get(motif, "Compare your move with the engine's line and ask what it saw that you did not.")

        line = " ".join(facts.get("best_line", [])[:5])
        tail = f" The engine's line ran {line}." if line else ""
        return self._wrap(f"{headline} {lesson}{tail}", learner, "mistake")

    def build_lesson(self, learner: LearnerContext, topic: str, reason: str) -> CoachingResponse:
        response = self._wrap(
            f"Lesson on {topic}. {reason} Work through the example position, then answer the check.",
            learner,
            "lesson",
        )
        # A template cannot invent teaching positions; the caller supplies them from the
        # puzzle bank instead.
        response.structured = None
        return response

    def check_feedback(self, learner: LearnerContext, facts: dict[str, Any]) -> CoachingResponse:
        if facts["correct"]:
            text = f"Correct. {facts['answer']} is the move."
        else:
            text = (
                f"Not this time. You played {facts['student_answer']}; the move that works is "
                f"{facts['answer']}. Set the position up again and look for it."
            )
        return self._wrap(text, learner, "check")

    def assessment_summary(self, learner: LearnerContext, facts: dict[str, Any]) -> CoachingResponse:
        weaknesses = learner.weakness_text or "nothing conclusive yet"
        return self._wrap(
            f"Your rating estimate is {facts['rating']}. The clearest things to work on are: {weaknesses}. "
            "Start with the first one; it costs you the most points.",
            learner,
            "summary",
        )

    def chat(self, learner: LearnerContext, question: str, history: list[dict[str, str]]) -> CoachingResponse:
        return self._wrap(
            "Conversational coaching needs a coaching model. Set ANTHROPIC_API_KEY to enable it. "
            "In the meantime, game review, puzzles and lessons all still work.",
            learner,
            "chat",
        )


# ------------------------------------------------------------------ selection
_brain: CoachingBrain | None = None


def get_brain() -> CoachingBrain:
    global _brain
    if _brain is None:
        _brain = ClaudeBrain() if settings.anthropic_api_key else TemplateBrain()
        log.info("Coaching brain: %s", _brain.source)
    return _brain


def reset_brain() -> None:
    """Used by tests and by configuration reloads."""
    global _brain
    _brain = None
