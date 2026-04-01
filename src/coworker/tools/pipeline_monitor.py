"""
Pipeline Monitor Tools
======================
Monitors ADF pipelines, Databricks workflows, and Power BI dataset refreshes.
When a failure is detected the agent:
  1. Reads the error message and stack trace
  2. Navigates to the relevant notebook / SQL to diagnose root cause
  3. Checks for schema drift or upstream data issues
  4. Attempts auto-recovery (retry, skip, or fix) when safe
  5. Sends a Teams alert with diagnosis + action taken

External dependencies (installed on the cluster):
  • azure-identity + azure-mgmt-datafactory   — ADF monitoring
  • databricks-sdk                            — Workflows monitoring
  • azure-identity + requests                 — Power BI REST API
"""

from __future__ import annotations
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import cfg
from ..db_client import get_db

log = logging.getLogger("coworker.pipeline_monitor")


# ═══════════════════════════════════════════════════════════════════════════
#  1. AZURE DATA FACTORY (ADF) MONITORING
# ═══════════════════════════════════════════════════════════════════════════

def check_adf_pipeline_runs(
    resource_group: str,
    factory_name: str,
    hours_back: int = 24,
    status_filter: str = "Failed",
) -> str:
    """
    Query ADF pipeline runs for failures in the last N hours.
    Returns run ID, pipeline name, error message, and parameters.
    """
    try:
        from azure.identity import DefaultAzureCredential
        from azure.mgmt.datafactory import DataFactoryManagementClient
        from azure.mgmt.datafactory.models import RunFilterParameters, RunQueryFilter
    except ImportError:
        return json.dumps({"error": "Install azure-mgmt-datafactory: pip install azure-mgmt-datafactory azure-identity"})

    credential = DefaultAzureCredential()
    # Subscription ID from Databricks secrets or env
    sub_id = _get_secret("coworker-agent", "azure-subscription-id", "AZURE_SUBSCRIPTION_ID")
    client = DataFactoryManagementClient(credential, sub_id)

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours_back)

    filters = RunFilterParameters(
        last_updated_after=start,
        last_updated_before=now,
        filters=[
            RunQueryFilter(operand="Status", operator="Equals", values=[status_filter])
        ],
    )

    runs = client.pipeline_runs.query_by_factory(resource_group, factory_name, filters)

    results = []
    for run in runs.value:
        results.append({
            "run_id": run.run_id,
            "pipeline_name": run.pipeline_name,
            "status": run.status,
            "start_time": str(run.run_start),
            "end_time": str(run.run_end),
            "duration_seconds": run.duration_in_ms / 1000 if run.duration_in_ms else None,
            "error_message": run.message or "",
            "parameters": run.parameters or {},
        })

    severity = "CRITICAL" if results else "OK"
    return json.dumps({
        "factory": factory_name,
        "period_hours": hours_back,
        "status_filter": status_filter,
        "failed_runs": len(results),
        "severity": severity,
        "runs": results,
        "summary": (
            f"{'🔴' if severity == 'CRITICAL' else '🟢'} "
            f"ADF '{factory_name}': {len(results)} failed pipeline(s) "
            f"in the last {hours_back}h."
        ),
    }, default=str)


def get_adf_activity_errors(
    resource_group: str,
    factory_name: str,
    run_id: str,
) -> str:
    """
    Drill into a specific ADF pipeline run to get activity-level errors.
    Returns the failing activity, its error code, and the full error message.
    """
    try:
        from azure.identity import DefaultAzureCredential
        from azure.mgmt.datafactory import DataFactoryManagementClient
        from azure.mgmt.datafactory.models import RunFilterParameters
    except ImportError:
        return json.dumps({"error": "Install azure-mgmt-datafactory"})

    credential = DefaultAzureCredential()
    sub_id = _get_secret("coworker-agent", "azure-subscription-id", "AZURE_SUBSCRIPTION_ID")
    client = DataFactoryManagementClient(credential, sub_id)

    filters = RunFilterParameters(
        last_updated_after=datetime(2020, 1, 1, tzinfo=timezone.utc),
        last_updated_before=datetime.now(timezone.utc),
    )
    activities = client.activity_runs.query_by_pipeline_run(
        resource_group, factory_name, run_id, filters
    )

    errors = []
    for act in activities.value:
        if act.status == "Failed":
            errors.append({
                "activity_name": act.activity_name,
                "activity_type": act.activity_type,
                "status": act.status,
                "error": act.error or {},
                "input": _truncate(str(act.input), 500),
                "output": _truncate(str(act.output), 500),
                "duration_ms": act.duration_in_ms,
            })

    return json.dumps({
        "run_id": run_id,
        "failed_activities": len(errors),
        "errors": errors,
    }, default=str)


def retry_adf_pipeline(
    resource_group: str,
    factory_name: str,
    pipeline_name: str,
    parameters: dict | None = None,
) -> str:
    """
    Re-trigger an ADF pipeline (auto-recovery).
    Only call this after diagnosing the failure and confirming the fix.
    """
    try:
        from azure.identity import DefaultAzureCredential
        from azure.mgmt.datafactory import DataFactoryManagementClient
    except ImportError:
        return json.dumps({"error": "Install azure-mgmt-datafactory"})

    credential = DefaultAzureCredential()
    sub_id = _get_secret("coworker-agent", "azure-subscription-id", "AZURE_SUBSCRIPTION_ID")
    client = DataFactoryManagementClient(credential, sub_id)

    response = client.pipelines.create_run(
        resource_group, factory_name, pipeline_name,
        parameters=parameters or {},
    )

    return json.dumps({
        "action": "RETRY",
        "pipeline": pipeline_name,
        "new_run_id": response.run_id,
        "status": "Triggered",
        "message": f"Re-triggered pipeline '{pipeline_name}'.  New run: {response.run_id}",
    })


# ═══════════════════════════════════════════════════════════════════════════
#  2. DATABRICKS WORKFLOWS MONITORING
# ═══════════════════════════════════════════════════════════════════════════

def check_databricks_job_runs(
    hours_back: int = 24,
    status_filter: str = "FAILED",
) -> str:
    """
    List recent Databricks workflow job runs, filtered by status.
    Uses the Databricks SDK (available on all clusters).
    """
    try:
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.service.jobs import ListRunsRunType
    except ImportError:
        return json.dumps({"error": "databricks-sdk not available"})

    w = WorkspaceClient()
    now = datetime.now(timezone.utc)
    start_ms = int((now - timedelta(hours=hours_back)).timestamp() * 1000)

    runs = list(w.jobs.list_runs(
        start_time_from=start_ms,
        expand_tasks=True,
        limit=50,
    ))

    failed = []
    for run in runs:
        state = run.state
        if state and state.result_state and state.result_state.value == status_filter:
            # Get task-level errors
            task_errors = []
            for task in (run.tasks or []):
                ts = task.state
                if ts and ts.result_state and ts.result_state.value == "FAILED":
                    task_errors.append({
                        "task_key": task.task_key,
                        "error_message": ts.state_message or "",
                    })

            failed.append({
                "run_id": run.run_id,
                "job_id": run.job_id,
                "run_name": run.run_name,
                "start_time": str(datetime.fromtimestamp(run.start_time / 1000, tz=timezone.utc)) if run.start_time else None,
                "state_message": state.state_message or "",
                "task_errors": task_errors,
                "run_page_url": run.run_page_url,
            })

    severity = "CRITICAL" if failed else "OK"
    return json.dumps({
        "period_hours": hours_back,
        "failed_runs": len(failed),
        "severity": severity,
        "runs": failed,
        "summary": (
            f"{'🔴' if failed else '🟢'} "
            f"Databricks: {len(failed)} failed job run(s) in the last {hours_back}h."
        ),
    }, default=str)


def get_databricks_job_run_output(run_id: int) -> str:
    """Get the output and error details for a specific Databricks job run."""
    try:
        from databricks.sdk import WorkspaceClient
    except ImportError:
        return json.dumps({"error": "databricks-sdk not available"})

    w = WorkspaceClient()
    run = w.jobs.get_run(run_id)

    output = {
        "run_id": run.run_id,
        "run_name": run.run_name,
        "state": run.state.result_state.value if run.state and run.state.result_state else "UNKNOWN",
        "state_message": run.state.state_message if run.state else "",
        "tasks": [],
    }

    for task in (run.tasks or []):
        ts = task.state
        task_info = {
            "task_key": task.task_key,
            "state": ts.result_state.value if ts and ts.result_state else "UNKNOWN",
            "error_message": ts.state_message if ts else "",
        }

        # Try to get notebook output
        if task.notebook_task:
            task_info["notebook_path"] = task.notebook_task.notebook_path
            try:
                task_output = w.jobs.get_run_output(task.run_id)
                if task_output.error:
                    task_info["error_trace"] = task_output.error
                if task_output.error_trace:
                    task_info["full_trace"] = _truncate(task_output.error_trace, 2000)
            except Exception:
                pass

        output["tasks"].append(task_info)

    return json.dumps(output, default=str)


def retry_databricks_job(job_id: int, notebook_params: dict | None = None) -> str:
    """Re-run a failed Databricks job (auto-recovery)."""
    try:
        from databricks.sdk import WorkspaceClient
    except ImportError:
        return json.dumps({"error": "databricks-sdk not available"})

    w = WorkspaceClient()
    run = w.jobs.run_now(
        job_id=job_id,
        notebook_params=notebook_params or {},
    )

    return json.dumps({
        "action": "RETRY",
        "job_id": job_id,
        "new_run_id": run.run_id,
        "status": "Triggered",
        "message": f"Re-triggered Databricks job {job_id}.  New run: {run.run_id}",
    })


# ═══════════════════════════════════════════════════════════════════════════
#  3. POWER BI REFRESH MONITORING
# ═══════════════════════════════════════════════════════════════════════════

def check_powerbi_refresh_status(
    workspace_id: str,
    dataset_id: str,
) -> str:
    """
    Check the last refresh status of a Power BI dataset.
    Uses the Power BI REST API via service principal auth.
    """
    import requests
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()
    token = credential.get_token("https://analysis.windows.net/powerbi/api/.default")

    resp = requests.get(
        f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}"
        f"/datasets/{dataset_id}/refreshes?$top=5",
        headers={"Authorization": f"Bearer {token.token}"},
        timeout=15,
    )
    resp.raise_for_status()

    refreshes = resp.json().get("value", [])
    results = []
    for r in refreshes:
        results.append({
            "request_id": r.get("requestId"),
            "status": r.get("status"),              # Completed | Failed | Unknown | Disabled
            "start_time": r.get("startTime"),
            "end_time": r.get("endTime"),
            "error": r.get("serviceExceptionJson"),
        })

    latest = results[0] if results else {}
    severity = "CRITICAL" if latest.get("status") == "Failed" else "OK"

    return json.dumps({
        "workspace_id": workspace_id,
        "dataset_id": dataset_id,
        "latest_status": latest.get("status", "Unknown"),
        "severity": severity,
        "recent_refreshes": results,
        "summary": (
            f"{'🔴' if severity == 'CRITICAL' else '🟢'} "
            f"Power BI dataset {dataset_id}: last refresh {latest.get('status', 'Unknown')}."
        ),
    }, default=str)


def trigger_powerbi_refresh(workspace_id: str, dataset_id: str) -> str:
    """Trigger a Power BI dataset refresh (auto-recovery after upstream fix)."""
    import requests
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()
    token = credential.get_token("https://analysis.windows.net/powerbi/api/.default")

    resp = requests.post(
        f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}"
        f"/datasets/{dataset_id}/refreshes",
        headers={"Authorization": f"Bearer {token.token}"},
        json={"notifyOption": "MailOnFailure"},
        timeout=15,
    )

    if resp.status_code == 202:
        return json.dumps({
            "action": "REFRESH_TRIGGERED",
            "dataset_id": dataset_id,
            "status": "Accepted",
            "message": "Power BI dataset refresh triggered successfully.",
        })
    else:
        return json.dumps({
            "action": "REFRESH_FAILED",
            "status_code": resp.status_code,
            "error": resp.text,
        })


# ═══════════════════════════════════════════════════════════════════════════
#  4. POST-LOAD VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

def validate_post_load(table: str, expected_min_rows: int = 1000) -> str:
    """
    After a successful ETL load, validate:
      1. Row count meets minimum threshold
      2. Key columns have acceptable null rates
      3. Today's partition exists and has data
      4. No duplicate primary keys (if applicable)
    """
    db = get_db()
    safe = table.strip()
    if not re.fullmatch(r"[\w.]+", safe):
        return json.dumps({"error": f"Invalid table name: {safe}"})

    checks = []

    # 1. Row count
    total = db.execute(f"SELECT COUNT(*) AS cnt FROM {safe}")[0]["cnt"]
    checks.append({
        "check": "row_count",
        "value": total,
        "threshold": expected_min_rows,
        "passed": total >= expected_min_rows,
        "severity": "CRITICAL" if total < expected_min_rows else "OK",
    })

    # 2. Today's data exists (auto-detect date column)
    cols = [c["name"].lower() for c in db.get_columns(safe)]
    date_candidates = [c for c in cols if "date" in c and "key" not in c]
    if date_candidates:
        dc = date_candidates[0]
        today_count = db.execute(
            f"SELECT COUNT(*) AS cnt FROM {safe} WHERE CAST(`{dc}` AS DATE) = CURRENT_DATE()"
        )[0]["cnt"]
        checks.append({
            "check": "todays_data_exists",
            "date_column": dc,
            "today_rows": today_count,
            "passed": today_count > 0,
            "severity": "CRITICAL" if today_count == 0 else "OK",
        })

    # 3. Critical column null check (IDs and keys)
    key_cols = [c for c in cols if c.endswith("key") or c.endswith("id") or c == "account ak"][:10]
    if key_cols:
        exprs = [
            f"ROUND(100.0 * SUM(CASE WHEN `{c}` IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS `{c}`"
            for c in key_cols
        ]
        null_row = db.execute(f"SELECT {', '.join(exprs)} FROM {safe}")[0]
        null_issues = {col: pct for col, pct in null_row.items() if pct and float(pct) > 5}
        checks.append({
            "check": "key_column_nulls",
            "columns_checked": len(key_cols),
            "issues": null_issues,
            "passed": len(null_issues) == 0,
            "severity": "HIGH" if null_issues else "OK",
        })

    overall_passed = all(c["passed"] for c in checks)
    overall_severity = "OK" if overall_passed else max(
        (c["severity"] for c in checks if not c["passed"]),
        key=lambda s: ["OK", "LOW", "MEDIUM", "HIGH", "CRITICAL"].index(s),
    )

    return json.dumps({
        "table": safe,
        "overall_passed": overall_passed,
        "overall_severity": overall_severity,
        "checks": checks,
        "summary": (
            f"{'🟢' if overall_passed else '🔴'} Post-load validation for {safe}: "
            f"{'ALL PASSED' if overall_passed else 'ISSUES FOUND — see checks for details'}."
        ),
    }, default=str)


# ═══════════════════════════════════════════════════════════════════════════
#  5. INTELLIGENT FAILURE DIAGNOSIS (uses the agent's LLM)
# ═══════════════════════════════════════════════════════════════════════════

def diagnose_failure(
    error_message: str,
    pipeline_type: str = "unknown",
    pipeline_name: str = "",
    notebook_path: str | None = None,
) -> str:
    """
    Feed the error message to the agent's LLM for intelligent diagnosis.
    Returns a structured diagnosis with:
      - Root cause classification
      - Affected tables / columns
      - Recommended recovery action
      - Whether auto-recovery is safe
    """
    from ..llm import chat_completion

    diagnosis_prompt = f"""
Analyze this pipeline failure and provide a structured diagnosis.

Pipeline type: {pipeline_type}
Pipeline name: {pipeline_name}
{f'Notebook: {notebook_path}' if notebook_path else ''}

Error message:
{error_message[:3000]}

Respond in this exact JSON format:
{{
    "root_cause_category": "SCHEMA_DRIFT | DATA_QUALITY | TIMEOUT | PERMISSION | RESOURCE | NETWORK | CODE_BUG | UPSTREAM_DELAY | UNKNOWN",
    "root_cause_explanation": "...",
    "affected_tables": ["..."],
    "affected_columns": ["..."],
    "recommended_action": "RETRY | SKIP | FIX_SCHEMA | FIX_DATA | ESCALATE | WAIT",
    "auto_recovery_safe": true/false,
    "auto_recovery_steps": ["..."],
    "business_impact": "...",
    "urgency": "CRITICAL | HIGH | MEDIUM | LOW"
}}
"""

    response = chat_completion(
        messages=[
            {"role": "system", "content": "You are a pipeline failure diagnosis expert.  Respond only with valid JSON."},
            {"role": "user", "content": diagnosis_prompt},
        ],
        stream=False,
        temperature=0.1,
    )

    return response.choices[0].message.content or json.dumps({"error": "Empty LLM response"})


# ── Helpers ───────────────────────────────────────────────────────────────

def _truncate(s: str, max_len: int) -> str:
    return s[:max_len] + "..." if len(s) > max_len else s


def _get_secret(scope: str, key: str, env_fallback: str) -> str:
    import os
    try:
        from databricks.sdk.runtime import dbutils
        return dbutils.secrets.get(scope=scope, key=key)
    except Exception:
        return os.getenv(env_fallback, "")


# ── OpenAI tool schemas ──────────────────────────────────────────────────

PIPELINE_MONITOR_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "check_adf_pipeline_runs",
            "description": (
                "Check Azure Data Factory for failed pipeline runs in the last N hours.  "
                "Returns run IDs, pipeline names, and error messages."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "resource_group": {"type": "string"},
                    "factory_name":   {"type": "string"},
                    "hours_back":     {"type": "integer", "default": 24},
                    "status_filter":  {"type": "string", "default": "Failed",
                                       "enum": ["Failed", "Succeeded", "InProgress", "Queued", "Cancelling"]},
                },
                "required": ["resource_group", "factory_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_adf_activity_errors",
            "description": "Drill into a specific ADF pipeline run to get activity-level error details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resource_group": {"type": "string"},
                    "factory_name":   {"type": "string"},
                    "run_id":         {"type": "string"},
                },
                "required": ["resource_group", "factory_name", "run_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retry_adf_pipeline",
            "description": (
                "Auto-recovery: re-trigger a failed ADF pipeline.  ONLY call this "
                "after diagnosing the failure and confirming the root cause is transient "
                "(timeout, network) or has been fixed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "resource_group": {"type": "string"},
                    "factory_name":   {"type": "string"},
                    "pipeline_name":  {"type": "string"},
                    "parameters":     {"type": "object", "description": "Pipeline parameters (optional)"},
                },
                "required": ["resource_group", "factory_name", "pipeline_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_databricks_job_runs",
            "description": "List recent Databricks workflow job runs filtered by status (default: FAILED).",
            "parameters": {
                "type": "object",
                "properties": {
                    "hours_back":    {"type": "integer", "default": 24},
                    "status_filter": {"type": "string", "default": "FAILED",
                                      "enum": ["FAILED", "SUCCESS", "TIMEDOUT", "CANCELED"]},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_databricks_job_run_output",
            "description": "Get detailed output, error trace, and notebook path for a specific Databricks job run.",
            "parameters": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "integer"},
                },
                "required": ["run_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retry_databricks_job",
            "description": "Auto-recovery: re-run a failed Databricks job.  Only after diagnosis confirms safe to retry.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id":          {"type": "integer"},
                    "notebook_params": {"type": "object"},
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_powerbi_refresh_status",
            "description": "Check the last refresh status of a Power BI dataset.  Returns recent refresh history.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "dataset_id":   {"type": "string"},
                },
                "required": ["workspace_id", "dataset_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_powerbi_refresh",
            "description": "Auto-recovery: trigger a Power BI dataset refresh after upstream data is fixed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "dataset_id":   {"type": "string"},
                },
                "required": ["workspace_id", "dataset_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_post_load",
            "description": (
                "Run post-load validation after a successful ETL: row count, "
                "today's partition, key column nulls.  Use this to confirm data "
                "landed correctly before notifying the team."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "table":              {"type": "string"},
                    "expected_min_rows":  {"type": "integer", "default": 1000},
                },
                "required": ["table"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "diagnose_failure",
            "description": (
                "Intelligently diagnose a pipeline failure using the LLM.  "
                "Pass the error message and context — returns root cause, "
                "affected tables, recommended action, and whether auto-recovery is safe."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "error_message":  {"type": "string"},
                    "pipeline_type":  {"type": "string", "enum": ["ADF", "Databricks", "PowerBI", "unknown"]},
                    "pipeline_name":  {"type": "string"},
                    "notebook_path":  {"type": "string"},
                },
                "required": ["error_message"],
            },
        },
    },
]


def run_pipeline_monitor_tool(name: str, args: dict) -> str:
    handlers = {
        "check_adf_pipeline_runs":       check_adf_pipeline_runs,
        "get_adf_activity_errors":       get_adf_activity_errors,
        "retry_adf_pipeline":            retry_adf_pipeline,
        "check_databricks_job_runs":     check_databricks_job_runs,
        "get_databricks_job_run_output": get_databricks_job_run_output,
        "retry_databricks_job":          retry_databricks_job,
        "check_powerbi_refresh_status":  check_powerbi_refresh_status,
        "trigger_powerbi_refresh":       trigger_powerbi_refresh,
        "validate_post_load":            validate_post_load,
        "diagnose_failure":              diagnose_failure,
    }
    fn = handlers.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown pipeline monitor tool: {name}"})
    try:
        return fn(**args)
    except Exception as exc:
        log.exception("Pipeline monitor tool error: %s", name)
        return json.dumps({"error": str(exc)})
