"""Purge old conversation history from Delta table."""
from src.coworker.memory import purge_old_conversations

deleted = purge_old_conversations(hours=24)
print(f"Purged {deleted} old conversation rows.")
