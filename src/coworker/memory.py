"""
Conversation Memory — Delta table-backed
=========================================
Stores conversation history so the agent can:
  • Resume conversations across sessions (Teams → close → reopen)
  • Reference what was discussed earlier ("like we talked about yesterday")
  • Build a profile of frequently asked questions

Delta table schema:
  conversation_id   STRING   (per-user or per-channel thread)
  turn_index        INT
  role              STRING   (system | user | assistant | tool)
  content           STRING   (message text or JSON-serialised tool call)
  tool_call_id      STRING   (nullable)
  created_at        TIMESTAMP
"""

from __future__ import annotations
import json
from datetime import datetime, timezone

from .config import cfg
from .db_client import get_db

_MEM_TABLE = f"{cfg.AGENT_CATALOG}.{cfg.AGENT_SCHEMA}.conversations"


def ensure_table() -> None:
    get_db().execute(f"""
        CREATE TABLE IF NOT EXISTS {_MEM_TABLE} (
            conversation_id STRING,
            turn_index      INT,
            role            STRING,
            content         STRING,
            tool_call_id    STRING,
            created_at      TIMESTAMP
        )
        USING DELTA
        PARTITIONED BY (conversation_id)
        TBLPROPERTIES ('delta.autoOptimize.optimizeWrite' = 'true')
    """)


def save_turn(
    conversation_id: str,
    turn_index: int,
    role: str,
    content: str,
    tool_call_id: str | None = None,
) -> None:
    """Append a single turn to the conversation history."""
    ensure_table()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    escaped_content = content.replace("'", "''")
    tcid = f"'{tool_call_id}'" if tool_call_id else "NULL"
    get_db().execute(f"""
        INSERT INTO {_MEM_TABLE}
        (conversation_id, turn_index, role, content, tool_call_id, created_at)
        VALUES ('{conversation_id}', {turn_index}, '{role}',
                '{escaped_content}', {tcid}, TIMESTAMP '{ts}')
    """)


def load_history(conversation_id: str, max_turns: int = 50) -> list[dict]:
    """
    Load the most recent turns for a conversation, formatted as OpenAI messages.
    """
    ensure_table()
    rows = get_db().execute(f"""
        SELECT role, content, tool_call_id
        FROM {_MEM_TABLE}
        WHERE conversation_id = '{conversation_id}'
        ORDER BY turn_index DESC
        LIMIT {max_turns}
    """)

    # Reverse to chronological order
    messages = []
    for d in reversed(rows):
        msg = {"role": d["role"], "content": d["content"]}
        if d.get("tool_call_id"):
            msg["tool_call_id"] = d["tool_call_id"]
        messages.append(msg)
    return messages


def purge_old_conversations(hours: int | None = None) -> int:
    """Delete conversations older than the TTL.  Returns rows deleted."""
    ttl = hours or cfg.CONVERSATION_TTL_HOURS
    ensure_table()
    db = get_db()

    count_before = db.execute(f"SELECT COUNT(*) AS cnt FROM {_MEM_TABLE}")[0]["cnt"]
    db.execute(f"""
        DELETE FROM {_MEM_TABLE}
        WHERE created_at < TIMESTAMPADD(HOUR, -{ttl}, CURRENT_TIMESTAMP())
    """)
    count_after = db.execute(f"SELECT COUNT(*) AS cnt FROM {_MEM_TABLE}")[0]["cnt"]
    return count_before - count_after
