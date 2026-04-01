"""
Configuration — reads all credentials from Databricks Secret Scopes.

Secret scope layout (configure via Databricks CLI or UI):
  Scope: "coworker-agent"
    ai-foundry-endpoint     → Azure AI Foundry project endpoint
    ai-foundry-key          → API key (or use managed identity — see below)
    teams-app-id            → Azure Bot registration app ID
    teams-app-password      → Azure Bot registration app password
    alert-webhook-url       → Incoming Webhook URL for proactive alerts channel

Usage in a Databricks notebook or job:
    from coworker.config import cfg
    print(cfg.FOUNDRY_ENDPOINT)

Outside Databricks (local / unit tests) the values fall back to env vars.
"""

from __future__ import annotations
import os


def _secret(scope: str, key: str, env_fallback: str) -> str:
    """
    Try Databricks Secret scope first; fall back to environment variable.
    Avoids ImportError when running unit tests outside a Databricks cluster.
    """
    try:
        from databricks.sdk.runtime import dbutils  # noqa: PLC0415
        return dbutils.secrets.get(scope=scope, key=key)
    except Exception:
        val = os.getenv(env_fallback, "")
        if not val:
            raise EnvironmentError(
                f"Secret '{scope}/{key}' not found and env var "
                f"'{env_fallback}' is not set."
            )
        return val


def _secret_optional(scope: str, key: str, env_fallback: str) -> str:
    """Like _secret but returns empty string instead of raising."""
    try:
        from databricks.sdk.runtime import dbutils  # noqa: PLC0415
        return dbutils.secrets.get(scope=scope, key=key)
    except Exception:
        return os.getenv(env_fallback, "")


class Config:
    # ── Azure AI Foundry / GPT-5.1 ──────────────────────────────────────────
    FOUNDRY_ENDPOINT: str = _secret(
        "coworker-agent", "ai-foundry-endpoint", "AZURE_AI_FOUNDRY_ENDPOINT"
    )
    FOUNDRY_API_KEY: str = _secret(
        "coworker-agent", "ai-foundry-key", "AZURE_AI_FOUNDRY_KEY"
    )
    # Deployment name as configured in your AI Foundry project
    GPT_DEPLOYMENT: str = os.getenv("GPT_DEPLOYMENT_NAME", "gpt-5.1")
    # API version that supports GPT-5.1 tool calling
    OPENAI_API_VERSION: str = os.getenv("OPENAI_API_VERSION", "2025-04-01-preview")

    # ── Teams / Azure Bot Framework ──────────────────────────────────────────
    TEAMS_APP_ID: str = _secret(
        "coworker-agent", "teams-app-id", "TEAMS_APP_ID"
    )
    TEAMS_APP_PASSWORD: str = _secret(
        "coworker-agent", "teams-app-password", "TEAMS_APP_PASSWORD"
    )

    # ── Proactive alerts (Teams Incoming Webhook) ────────────────────────────
    ALERT_WEBHOOK_URL: str = _secret(
        "coworker-agent", "alert-webhook-url", "TEAMS_ALERT_WEBHOOK_URL"
    )

    # ── Databricks / Unity Catalog ───────────────────────────────────────────
    # The catalog and schema where the agent stores its state tables
    AGENT_CATALOG: str = os.getenv("AGENT_CATALOG", "miral_coworker")
    AGENT_SCHEMA: str  = os.getenv("AGENT_SCHEMA",  "agent_state")

    # ── SQL Warehouse (for Databricks Apps / serverless mode) ────────────────
    # When set, the agent uses databricks-sql-connector instead of SparkSession.
    # This allows the FastAPI app to run as a Databricks App (no cluster needed).
    # Format: /sql/1.0/warehouses/<warehouse-id>
    SQL_WAREHOUSE_PATH: str = _secret_optional(
        "coworker-agent", "sql-warehouse-path", "SQL_WAREHOUSE_PATH"
    )
    DATABRICKS_HOST: str = os.getenv(
        "DATABRICKS_HOST",
        os.getenv("DATABRICKS_SERVER_HOSTNAME", ""),
    )
    DATABRICKS_TOKEN: str = _secret_optional(
        "coworker-agent", "databricks-token", "DATABRICKS_TOKEN"
    )

    # Tables watched by the proactive monitor (comma-separated)
    MONITORED_TABLES: list[str] = [
        t.strip() for t in os.getenv(
            "MONITORED_TABLES",
            "park_ops.tbvw_attendance,"
            "park_ops.tbvw_sales_transactions,"
            "park_ops.tbvw_daily_revenue_data_ss",
        ).split(",") if t.strip()
    ]

    # How many days of history to use for anomaly baselines
    BASELINE_DAYS: int = int(os.getenv("BASELINE_DAYS", "30"))

    # Maximum rows the DQ tool will scan (prevents accidental full-table scans)
    DQ_SAMPLE_ROWS: int = int(os.getenv("DQ_SAMPLE_ROWS", "1_000_000"))

    # ── Agent behaviour ───────────────────────────────────────────────────────
    MAX_TOOL_ROUNDS: int = int(os.getenv("MAX_TOOL_ROUNDS", "10"))
    CONVERSATION_TTL_HOURS: int = int(os.getenv("CONVERSATION_TTL_HOURS", "24"))


cfg = Config()
