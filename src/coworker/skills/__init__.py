"""
Skills Framework
================
Each skill is a self-contained capability with:
  - name          : unique identifier
  - description   : what the skill does (used by the router for intent matching)
  - trigger_phrases: example phrases that should activate this skill
  - system_prompt : skill-specific instructions appended to the base prompt
  - tools         : subset of ALL_TOOLS this skill needs
  - max_rounds    : how many tool-call rounds this skill gets

The SkillRouter classifies user intent and selects the best skill.
The agent then runs only that skill's tools with its augmented prompt.
"""

from .registry import Skill, SkillRegistry, get_registry
from .router import SkillRouter

__all__ = ["Skill", "SkillRegistry", "SkillRouter", "get_registry"]
