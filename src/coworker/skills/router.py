"""
Skill Router — classifies user intent and selects the best skill.

Two-stage routing:
  1. Fast keyword match (zero LLM cost, <1ms)
  2. LLM-based classification (fallback when keywords are ambiguous)

The router returns a Skill object.  If no skill matches, it returns None
and the agent falls back to the general-purpose mode (all tools available).
"""

from __future__ import annotations
import json
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .registry import Skill, SkillRegistry

log = logging.getLogger("coworker.router")


class SkillRouter:
    """Routes user messages to the most appropriate skill."""

    def __init__(self, registry: "SkillRegistry"):
        self.registry = registry
        # Build keyword index: keyword → skill name
        self._keyword_index: dict[str, str] = {}
        for skill in registry.all_skills():
            for phrase in skill.trigger_phrases:
                # Index each word in the trigger phrase
                for word in phrase.lower().split():
                    if len(word) > 3:  # skip short words
                        self._keyword_index[word] = skill.name

    def route(self, user_message: str) -> "Skill | None":
        """
        Classify user intent and return the best skill.
        Returns None if no skill is a clear match (use general mode).
        """
        # Stage 1: Fast keyword scoring
        skill = self._keyword_route(user_message)
        if skill is not None:
            log.info("Keyword router → %s", skill.name)
            return skill

        # Stage 2: LLM-based classification
        skill = self._llm_route(user_message)
        if skill is not None:
            log.info("LLM router → %s", skill.name)
            return skill

        log.info("No skill matched → general mode")
        return None

    # ── Stage 1: Keyword scoring ──────────────────────────────────────────

    def _keyword_route(self, message: str) -> "Skill | None":
        """Score each skill by keyword overlap with the message."""
        words = set(re.findall(r"\w+", message.lower()))
        scores: dict[str, int] = {}

        for word in words:
            skill_name = self._keyword_index.get(word)
            if skill_name:
                scores[skill_name] = scores.get(skill_name, 0) + 1

        if not scores:
            return None

        # Need at least 2 keyword hits to be confident
        best_name = max(scores, key=scores.get)
        if scores[best_name] >= 2:
            return self.registry.get(best_name)

        return None  # ambiguous — fall through to LLM

    # ── Stage 2: LLM classification ───────────────────────────────────────

    def _llm_route(self, message: str) -> "Skill | None":
        """Use GPT-5.1 to classify intent when keywords are ambiguous."""
        from ..llm import chat_completion

        skill_descriptions = self.registry.build_router_context()

        classification_prompt = f"""Classify this user message into exactly one skill.

Available skills:
{skill_descriptions}

User message: "{message}"

Respond with ONLY the skill name (e.g. "pipeline_guardian") or "none" if no skill fits.
Do not explain — just the skill name."""

        try:
            response = chat_completion(
                messages=[
                    {"role": "system", "content": "You are a message classifier. Respond with only a skill name or 'none'."},
                    {"role": "user", "content": classification_prompt},
                ],
                stream=False,
                temperature=0.0,
            )

            skill_name = (response.choices[0].message.content or "").strip().lower()
            # Clean up any quotes or extra text
            skill_name = skill_name.strip('"\'').split()[0] if skill_name else "none"

            if skill_name == "none":
                return None

            return self.registry.get(skill_name)

        except Exception as exc:
            log.warning("LLM router failed: %s — falling back to general mode", exc)
            return None
