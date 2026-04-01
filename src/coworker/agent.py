"""
Agent Core — GPT-5.1 skill-based tool-calling loop
====================================================
Orchestrates the conversation:
  1. Accept user message
  2. Route to the best skill (keyword → LLM fallback)
  3. Inject the skill's system prompt and scoped tools
  4. Run the tool-calling loop with the skill's tools
  5. Persist the full conversation to Delta

Skills narrow the agent's focus: each skill has its own system prompt
addition, a curated subset of tools, and a max-round budget.  If no
skill matches, the agent falls back to general mode (all tools).
"""

from __future__ import annotations
import json
import logging
from typing import Generator

from .config import cfg
from .llm import chat_completion, SYSTEM_PROMPT
from .tools import ALL_TOOLS, dispatch_tool
from .skills import get_registry, SkillRouter
from . import memory

log = logging.getLogger("coworker.agent")


class CoworkerAgent:
    """
    Stateful agent instance.  One per conversation thread.

    Usage:
        agent = CoworkerAgent(conversation_id="teams-thread-abc123")
        reply = agent.handle_message("What data quality issues do we have?")
    """

    def __init__(self, conversation_id: str = "default"):
        self.conversation_id = conversation_id
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.turn_index: int = 0
        self._active_skill_name: str | None = None

        # Skill routing
        self._registry = get_registry()
        self._router = SkillRouter(self._registry)

        # Load prior conversation turns from Delta (if any)
        try:
            prior = memory.load_history(conversation_id)
            if prior:
                self.messages.extend(prior)
                self.turn_index = len(prior)
                log.info("Loaded %d prior turns for conversation %s", len(prior), conversation_id)
        except Exception as exc:
            log.warning("Could not load conversation history: %s", exc)

    # ── Public API ────────────────────────────────────────────────────────

    def handle_message(self, user_message: str) -> str:
        """
        Process a user message through the skill-routed agent loop.
        Returns the final assistant text response.
        """
        self.messages.append({"role": "user", "content": user_message})
        self._persist_turn("user", user_message)

        # Route to skill
        skill = self._router.route(user_message)
        if skill:
            self._active_skill_name = skill.name
            tools = skill.tools
            max_rounds = skill.max_rounds
            # Inject skill-specific instructions
            self._inject_skill_prompt(skill.name, skill.system_prompt)
            log.info("Skill activated: %s (%d tools, %d rounds)",
                     skill.name, len(tools), max_rounds)
        else:
            self._active_skill_name = None
            tools = ALL_TOOLS
            max_rounds = cfg.MAX_TOOL_ROUNDS
            log.info("General mode (all %d tools)", len(tools))

        final_text = self._agent_loop(tools, max_rounds)

        self._persist_turn("assistant", final_text)
        return final_text

    def handle_message_stream(self, user_message: str) -> Generator[str, None, None]:
        """
        Streaming variant — yields text chunks as they arrive from GPT-5.1.
        Tool calls are executed silently between streamed chunks.
        """
        self.messages.append({"role": "user", "content": user_message})
        self._persist_turn("user", user_message)

        # Route to skill
        skill = self._router.route(user_message)
        if skill:
            self._active_skill_name = skill.name
            tools = skill.tools
            max_rounds = skill.max_rounds
            self._inject_skill_prompt(skill.name, skill.system_prompt)
        else:
            self._active_skill_name = None
            tools = ALL_TOOLS
            max_rounds = cfg.MAX_TOOL_ROUNDS

        full_text = ""
        for chunk in self._agent_loop_stream(tools, max_rounds):
            full_text += chunk
            yield chunk

        self._persist_turn("assistant", full_text)

    @property
    def active_skill(self) -> str | None:
        """Name of the currently active skill, or None for general mode."""
        return self._active_skill_name

    def list_skills(self) -> list[dict]:
        """Return all registered skills with their descriptions."""
        return [
            {
                "name": s.name,
                "description": s.description,
                "trigger_phrases": s.trigger_phrases,
                "tool_count": len(s.tool_names),
            }
            for s in self._registry.all_skills()
        ]

    # ── Skill prompt injection ────────────────────────────────────────────

    def _inject_skill_prompt(self, skill_name: str, skill_prompt: str) -> None:
        """
        Add the skill's system prompt as an additional system message.
        This is appended after the base system prompt so the model sees both.
        """
        skill_msg = {
            "role": "system",
            "content": (
                f"[SKILL ACTIVATED: {skill_name}]\n\n"
                f"{skill_prompt}\n\n"
                f"You are now operating in {skill_name} mode.  "
                f"Use only the tools provided for this skill.  "
                f"When done, summarise your findings clearly."
            ),
        }
        self.messages.append(skill_msg)

    # ── Agent loop (non-streaming) ────────────────────────────────────────

    def _agent_loop(self, tools: list[dict], max_rounds: int) -> str:
        """
        Run the tool-calling loop until GPT-5.1 returns a final message
        or we hit the max rounds.
        """
        for round_num in range(max_rounds):
            response = chat_completion(
                messages=self.messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                stream=False,
            )

            choice = response.choices[0]
            message = choice.message

            # Append the assistant's reply (may contain tool_calls)
            self.messages.append(message.model_dump())

            # If no tool calls → done
            if not message.tool_calls:
                return message.content or ""

            # Execute each tool call
            for tc in message.tool_calls:
                fn_name = tc.function.name
                fn_args = tc.function.arguments

                log.info(
                    "[%s][round %d] Tool call: %s(%s)",
                    self._active_skill_name or "general",
                    round_num + 1, fn_name, fn_args[:200],
                )

                result = dispatch_tool(fn_name, fn_args)

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        # Safety net: if we exhaust rounds, ask the model to summarise
        self.messages.append({
            "role": "user",
            "content": (
                "You've used all available tool rounds.  Please summarise "
                "your findings so far and let me know if you need more investigation."
            ),
        })
        final = chat_completion(messages=self.messages, stream=False)
        text = final.choices[0].message.content or ""
        self.messages.append({"role": "assistant", "content": text})
        return text

    # ── Agent loop (streaming) ────────────────────────────────────────────

    def _agent_loop_stream(
        self, tools: list[dict], max_rounds: int,
    ) -> Generator[str, None, None]:
        """
        Streaming variant: yields text deltas.  When the model emits
        tool_calls, we execute them and re-enter the loop.
        """
        for round_num in range(max_rounds):
            stream = chat_completion(
                messages=self.messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                stream=True,
            )

            collected_text = ""
            tool_calls_acc: dict[int, dict] = {}

            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None:
                    continue

                if delta.content:
                    collected_text += delta.content
                    yield delta.content

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {
                                "id": tc_delta.id or "",
                                "name": "",
                                "arguments": "",
                            }
                        if tc_delta.id:
                            tool_calls_acc[idx]["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                tool_calls_acc[idx]["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                tool_calls_acc[idx]["arguments"] += tc_delta.function.arguments

            assistant_msg: dict = {"role": "assistant", "content": collected_text or None}
            if tool_calls_acc:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"],
                        },
                    }
                    for tc in sorted(tool_calls_acc.values(), key=lambda x: x["id"])
                ]

            self.messages.append(assistant_msg)

            if not tool_calls_acc:
                return

            for tc in sorted(tool_calls_acc.values(), key=lambda x: x["id"]):
                log.info("[%s][round %d] Tool call: %s",
                         self._active_skill_name or "general", round_num + 1, tc["name"])
                result = dispatch_tool(tc["name"], tc["arguments"])
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

    # ── Persistence ───────────────────────────────────────────────────────

    def _persist_turn(self, role: str, content: str) -> None:
        try:
            memory.save_turn(
                conversation_id=self.conversation_id,
                turn_index=self.turn_index,
                role=role,
                content=content,
            )
            self.turn_index += 1
        except Exception as exc:
            log.warning("Failed to persist turn: %s", exc)


# ── Convenience function ──────────────────────────────────────────────────

def ask(question: str, conversation_id: str = "default") -> str:
    """One-liner for notebook use: `from coworker.agent import ask; ask("...")`"""
    agent = CoworkerAgent(conversation_id=conversation_id)
    return agent.handle_message(question)
