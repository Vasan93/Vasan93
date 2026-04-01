"""Purge old conversation history from Delta table."""
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.coworker.memory import purge_old_conversations

deleted = purge_old_conversations(hours=24)
print(f"Purged {deleted} old conversation rows.")
