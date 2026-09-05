"""Recording coaching prompts and responses for later quality review."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import CoachingLog

log = get_logger(__name__)

# Transcripts can be long; keep them bounded so one runaway response cannot bloat the table.
MAX_STORED_CHARS = 20_000


def _trim(text: str) -> str:
    return text if len(text) <= MAX_STORED_CHARS else text[:MAX_STORED_CHARS] + "\n…[truncated]"


def record(
    db: Session | None,
    *,
    user_id: int | None,
    kind: str,
    system_prompt: str,
    user_prompt: str,
    response: str,
    source: str,
    model: str,
    language: str,
    prompt_version: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    latency_ms: int | None = None,
    guardrail_notes: str = "",
) -> None:
    """Store one exchange. Logging must never break coaching, so failures are swallowed."""
    if db is None:
        return
    try:
        db.add(
            CoachingLog(
                user_id=user_id,
                kind=kind,
                prompt_version=prompt_version,
                model=model,
                language=language,
                system_prompt=_trim(system_prompt),
                user_prompt=_trim(user_prompt),
                response=_trim(response),
                source=source,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                guardrail_notes=_trim(guardrail_notes),
            )
        )
        db.flush()
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Could not record coaching transcript: %s", exc)
