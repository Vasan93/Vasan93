"""
Agent Core — GPT-5.1 tool-calling loop
=======================================
Orchestrates the conversation:
  1. Accept user message
  2. Optionally load conversation history from Delta
  3. Call GPT-5.1 with all available tools
  4. If the model returns tool_calls → execute them → feed results back
  5. Repeat until the model returns a final text response
  6. Persist the full conversation to Delta
"""

from __future__ import annotations
import json
import logging
from typing import Generator

from .config import cfg
from .llm import chat_completion, SYSTEM_PROMPT
from .tools import ALL_TOOLS, dispatch_tool
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
        Process a user message through the full agent loop.
        Returns the final assistant text response.
        """
        self.messages.append({"role": "user", "content": user_message})
        self._persist_turn("user", user_message)

        final_text = self._agent_loop()

        self._persist_turn("assistant", final_text)
        return final_text

    def handle_message_stream(self, user_message: str) -> Generator[str, None, None]:
        """
        Streaming variant — yields text chunks as they arrive from GPT-5.1.
        Tool calls are executed silently between streamed chunks.
        """
        self.messages.append({"role": "user", "content": user_message})
        self._persist_turn("user", user_message)

        full_text = ""
        for chunk in self._agent_loop_stream():
            full_text += chunk
            yield chunk

        self._persist_turn("assistant", full_text)

    # ── Agent loop (non-streaming) ────────────────────────────────────────

    def _agent_loop(self) -> str:
        """
        Run the tool-calling loop until GPT-5.1 returns a final message
        or we hit the max rounds.
        """
        for round_num in range(cfg.MAX_TOOL_ROUNDS):
            response = chat_completion(
                messages=self.messages,
                tools=ALL_TOOLS,
                tool_choice="auto",
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
                    "[round %d] Tool call: %s(%s)",
                    round_num + 1, fn_name, fn_args[:200],
                )

                result = dispatch_tool(fn_name, fn_args)

                # Append tool result for GPT-5.1 to see
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

                log.info(
                    "[round %d] Tool result (%s): %s chars",
                    round_num + 1, fn_name, len(result),
                )

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

    def _agent_loop_stream(self) -> Generator[str, None, None]:
        """
        Streaming variant: yields text deltas.  When the model emits
        tool_calls, we execute them and re-enter the loop (the tool
        execution phase is not streamed).
        """
        for round_num in range(cfg.MAX_TOOL_ROUNDS):
            stream = chat_completion(
                messages=self.messages,
                tools=ALL_TOOLS,
                tool_choice="auto",
                stream=True,
            )

            collected_text = ""
            tool_calls_acc: dict[int, dict] = {}  # index → {id, name, arguments}

            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None:
                    continue

                # Stream text to caller
                if delta.content:
                    collected_text += delta.content
                    yield delta.content

                # Accumulate tool call fragments
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

            # Build the assistant message to append
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

            # If no tool calls → done
            if not tool_calls_acc:
                return

            # Execute tools (not streamed)
            for tc in sorted(tool_calls_acc.values(), key=lambda x: x["id"]):
                log.info("[round %d] Tool call: %s", round_num + 1, tc["name"])
                result = dispatch_tool(tc["name"], tc["arguments"])
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

            # Loop back to get the model's next response

    # ── Persistence ───────────────────────────────────────────────────────

    def _persist_turn(self, role: str, content: str) -> None:
        """Write a turn to Delta (fire-and-forget; failures are logged, not raised)."""
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
