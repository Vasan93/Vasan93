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

_MEM_TABLE = f"{cfg.AGENT_CATALOG}.{cfg.AGENT_SCHEMA}.conversations"


def _spark():
    from pyspark.sql import SparkSession
    s = SparkSession.getActiveSession()
    if s is None:
        raise RuntimeError("No active SparkSession.")
    return s


def ensure_table() -> None:
    _spark().sql(f"""
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
    spark = _spark()
    from pyspark.sql import Row

    row = Row(
        conversation_id=conversation_id,
        turn_index=turn_index,
        role=role,
        content=content,
        tool_call_id=tool_call_id,
        created_at=datetime.now(timezone.utc),
    )
    spark.createDataFrame([row]).write.format("delta").mode("append").saveAsTable(_MEM_TABLE)


def load_history(conversation_id: str, max_turns: int = 50) -> list[dict]:
    """
    Load the most recent turns for a conversation, formatted as OpenAI messages.
    """
    ensure_table()
    rows = _spark().sql(f"""
        SELECT role, content, tool_call_id
        FROM {_MEM_TABLE}
        WHERE conversation_id = '{conversation_id}'
        ORDER BY turn_index DESC
        LIMIT {max_turns}
    """).collect()

    # Reverse to chronological order
    messages = []
    for row in reversed(rows):
        d = row.asDict()
        msg = {"role": d["role"], "content": d["content"]}
        if d.get("tool_call_id"):
            msg["tool_call_id"] = d["tool_call_id"]
        messages.append(msg)
    return messages


def purge_old_conversations(hours: int | None = None) -> int:
    """Delete conversations older than the TTL.  Returns rows deleted."""
    ttl = hours or cfg.CONVERSATION_TTL_HOURS
    ensure_table()
    spark = _spark()

    count_before = spark.sql(f"SELECT COUNT(*) AS cnt FROM {_MEM_TABLE}").collect()[0]["cnt"]
    spark.sql(f"""
        DELETE FROM {_MEM_TABLE}
        WHERE created_at < TIMESTAMPADD(HOUR, -{ttl}, CURRENT_TIMESTAMP())
    """)
    count_after = spark.sql(f"SELECT COUNT(*) AS cnt FROM {_MEM_TABLE}").collect()[0]["cnt"]
    return count_before - count_after
