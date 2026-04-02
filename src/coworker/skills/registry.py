"""
Skill Registry — defines the Skill dataclass and the global registry.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Skill:
    """A self-contained agent capability."""

    name: str
    description: str
    trigger_phrases: list[str]
    system_prompt: str
    tool_names: list[str]
    max_rounds: int = 8
    # Populated at registration time from tool_names → actual tool schemas
    tools: list[dict] = field(default_factory=list, repr=False)


class SkillRegistry:
    """Holds all registered skills and resolves tool schemas."""

    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def all_skills(self) -> list[Skill]:
        return list(self._skills.values())

    def skill_names(self) -> list[str]:
        return list(self._skills.keys())

    def resolve_tools(self, all_tools: list[dict]) -> None:
        """
        After all tools are imported, call this once to populate each
        skill's `tools` list from its `tool_names`.
        """
        tool_index = {t["function"]["name"]: t for t in all_tools}
        for skill in self._skills.values():
            skill.tools = [
                tool_index[n] for n in skill.tool_names if n in tool_index
            ]

    def build_router_context(self) -> str:
        """
        Build a description block for the LLM-based router to classify intent.
        """
        lines = []
        for s in self._skills.values():
            triggers = ", ".join(f'"{t}"' for t in s.trigger_phrases[:4])
            lines.append(
                f"- **{s.name}**: {s.description}\n"
                f"  Triggers: {triggers}"
            )
        return "\n".join(lines)

    def register_custom_skill(
        self,
        name: str,
        description: str,
        trigger_phrases: list[str],
        system_prompt: str,
        tool_names: list[str],
        max_rounds: int = 8,
    ) -> Skill:
        """
        Register a custom skill at runtime and resolve its tools immediately.

        Example (notebook usage)::

            from src.coworker.skills import get_registry
            from src.coworker.tools import ALL_TOOLS

            reg = get_registry()
            reg.register_custom_skill(
                name="finance_analyst",
                description="Answers revenue and budget questions from the daily revenue view",
                trigger_phrases=["revenue", "budget", "forecast", "RPV", "yield"],
                system_prompt="You are a finance analyst. Focus on TBVW__DAILY_REVENUE_DATA_SS.",
                tool_names=["run_dq_query", "describe_table", "search_articles"],
                max_rounds=6,
            )
        """
        from ..tools import ALL_TOOLS

        skill = Skill(
            name=name,
            description=description,
            trigger_phrases=trigger_phrases,
            system_prompt=system_prompt,
            tool_names=tool_names,
            max_rounds=max_rounds,
        )
        self.register(skill)

        # Resolve tools for just this new skill
        tool_index = {t["function"]["name"]: t for t in ALL_TOOLS}
        skill.tools = [tool_index[n] for n in tool_names if n in tool_index]

        return skill


# ── Singleton ─────────────────────────────────────────────────────────────

_registry: SkillRegistry | None = None


def get_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        _register_all_skills(_registry)
        # Resolve tool schemas
        from ..tools import ALL_TOOLS
        _registry.resolve_tools(ALL_TOOLS)
    return _registry


def _register_all_skills(reg: SkillRegistry) -> None:
    """Import and register all built-in skills."""
    from .definitions import register_all
    register_all(reg)
