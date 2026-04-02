"""
FastAPI application — Databricks App
=====================================
Deploy as a Databricks App to expose the Co-Worker agent as a REST API.
Copilot Studio and Teams connect to these endpoints.

Endpoints:
  POST /chat              — Main conversation endpoint
  POST /chat/stream       — SSE streaming variant
  POST /bot/messages      — Teams Bot Framework webhook
  POST /monitor/trigger   — Manually trigger a proactive health check
  POST /monitor/pipelines — Check ADF + Databricks + Power BI pipelines
  GET  /knowledge-base    — List knowledge-base articles
  GET  /glossary          — Return the business glossary
  GET  /onboarding/{role} — Return an onboarding plan
  GET  /health            — Health check
"""

from __future__ import annotations
import json
import logging
import sys
import uuid
from pathlib import Path

# Ensure repo root is on sys.path so `from src.coworker...` works everywhere
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

log = logging.getLogger("coworker.app")

app = FastAPI(
    title="Co-Worker Agent — Yas Entertainment",
    version="1.0.0",
    description="Intelligent co-worker for data quality, code understanding, and onboarding.",
)


# ── Request / Response schemas ────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., description="User's question or command")
    conversation_id: str | None = Field(
        None,
        description="Thread ID to continue a conversation.  Omit to start a new one.",
    )
    user_name: str = Field("anonymous", description="Display name of the requester")
    stream: bool = Field(False, description="Set true for SSE streaming response")


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    active_skill: str | None = None
    tools_used: list[str] = []


class MonitorRequest(BaseModel):
    tables: list[str] | None = Field(
        None,
        description="Tables to check.  Omit to use the default monitored tables.",
    )


# ── Endpoints ─────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """Main conversation endpoint — Copilot Studio / Teams calls this."""
    from src.coworker.agent import CoworkerAgent

    conv_id = req.conversation_id or str(uuid.uuid4())

    try:
        agent = CoworkerAgent(conversation_id=conv_id)
        reply = agent.handle_message(req.message)
    except Exception as exc:
        log.exception("Agent error")
        raise HTTPException(status_code=500, detail=str(exc))

    return ChatResponse(
        conversation_id=conv_id,
        reply=reply,
        active_skill=agent.active_skill,
    )


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """SSE streaming variant for UIs that support real-time display."""
    from src.coworker.agent import CoworkerAgent

    conv_id = req.conversation_id or str(uuid.uuid4())
    agent = CoworkerAgent(conversation_id=conv_id)

    def event_generator():
        try:
            for chunk in agent.handle_message_stream(req.message):
                yield f"data: {json.dumps({'text': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True, 'conversation_id': conv_id})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/monitor/trigger")
def trigger_monitor(req: MonitorRequest):
    """Manually trigger the proactive health check."""
    from src.coworker.tools.data_quality import full_table_health
    from src.coworker.config import cfg

    tables = req.tables or cfg.MONITORED_TABLES
    results = {}
    for tbl in tables:
        try:
            results[tbl] = json.loads(full_table_health(tbl))
        except Exception as exc:
            results[tbl] = {"error": str(exc)}

    return {"tables_checked": len(tables), "results": results}


@app.get("/knowledge-base")
def list_kb(category: str | None = None, limit: int = 20):
    from src.coworker.tools.knowledge_base import list_articles
    return json.loads(list_articles(category=category, limit=limit))


@app.get("/skills")
def list_skills():
    """List all available agent skills with descriptions and triggers."""
    from src.coworker.skills import get_registry
    reg = get_registry()
    return {
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "trigger_phrases": s.trigger_phrases,
                "tool_count": len(s.tool_names),
                "max_rounds": s.max_rounds,
            }
            for s in reg.all_skills()
        ]
    }


@app.get("/glossary")
def glossary(term: str | None = None):
    from src.coworker.tools.onboarding import get_glossary
    return json.loads(get_glossary(term=term))


@app.get("/onboarding/{role}")
def onboarding(role: str):
    from src.coworker.tools.onboarding import get_onboarding_plan
    result = json.loads(get_onboarding_plan(role))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ── Teams Bot Framework webhook ───────────────────────────────────────────

_bot_handler = None

def _get_bot_handler():
    global _bot_handler
    if _bot_handler is None:
        from src.coworker.config import cfg
        try:
            from .teams_handler import TeamsBotHandler
        except ImportError:
            from app.teams_handler import TeamsBotHandler
        _bot_handler = TeamsBotHandler(cfg.TEAMS_APP_ID, cfg.TEAMS_APP_PASSWORD)
    return _bot_handler


@app.post("/bot/messages")
async def bot_messages(request: Request):
    """Azure Bot Framework webhook — Teams sends messages here."""
    handler = _get_bot_handler()
    return await handler.handle_activity(request)


# ── Pipeline monitoring endpoints ─────────────────────────────────────────

class PipelineCheckRequest(BaseModel):
    hours_back: int = Field(24, description="How many hours back to check")
    adf_resource_group: str | None = None
    adf_factory_name: str | None = None
    powerbi_workspace_id: str | None = None
    powerbi_dataset_id: str | None = None


@app.post("/monitor/pipelines")
def check_pipelines(req: PipelineCheckRequest):
    """Check all pipeline types (ADF + Databricks + Power BI) in one call."""
    from src.coworker.tools.pipeline_monitor import (
        check_adf_pipeline_runs,
        check_databricks_job_runs,
        check_powerbi_refresh_status,
    )

    results = {}

    # Databricks jobs (always available)
    try:
        results["databricks"] = json.loads(
            check_databricks_job_runs(hours_back=req.hours_back)
        )
    except Exception as exc:
        results["databricks"] = {"error": str(exc)}

    # ADF (if configured)
    if req.adf_resource_group and req.adf_factory_name:
        try:
            results["adf"] = json.loads(
                check_adf_pipeline_runs(
                    resource_group=req.adf_resource_group,
                    factory_name=req.adf_factory_name,
                    hours_back=req.hours_back,
                )
            )
        except Exception as exc:
            results["adf"] = {"error": str(exc)}

    # Power BI (if configured)
    if req.powerbi_workspace_id and req.powerbi_dataset_id:
        try:
            results["powerbi"] = json.loads(
                check_powerbi_refresh_status(
                    workspace_id=req.powerbi_workspace_id,
                    dataset_id=req.powerbi_dataset_id,
                )
            )
        except Exception as exc:
            results["powerbi"] = {"error": str(exc)}

    return {"period_hours": req.hours_back, "results": results}


@app.get("/health")
def health():
    return {"status": "ok", "service": "coworker-agent"}


# ── Databricks App entry point ────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
