"""
Pipeline Monitor Tools
======================
Full-stack pipeline monitoring for the Yas Entertainment / Miral Parks
data platform.

Architecture monitored:
  ADF (multi-source ingest)
    ├── SQL Server   ─┐
    ├── Oracle       ─┤─→ Landing Zone (ADLS) → Databricks Bronze
    ├── CRM API      ─┤                              ↓
    └── REST API     ─┘                         Databricks Silver
                                                      ↓
                                               Databricks Gold
                                                      ↓
                                                  Power BI

Key capabilities:
  • check_adf_by_source_type   — ADF failures grouped by SQL/Oracle/CRM/REST
  • check_databricks_by_layer  — Databricks failures grouped by Bronze/Silver/Gold
  • daily_pipeline_report      — Full end-to-end daily digest with LLM diagnosis
  • get_pipeline_cascade_impact — Trace ADF failure → Bronze → Silver → Gold → PBI
  • diagnose_failure            — LLM root-cause classification
  • Auto-recovery for transient failures (retry ADF / Databricks)

External dependencies:
  azure-identity + azure-mgmt-datafactory  (ADF)
  databricks-sdk                           (Databricks Workflows)
  requests                                 (Power BI REST API)
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

# ── Source/Layer detection helpers ───────────────────────────────────────────

def _detect_adf_source_type(pipeline_name: str) -> str:
    """Infer the source system from the ADF pipeline name."""
    n = pipeline_name.lower()
    if any(k in n for k in ("oracle", "_ora_", "_ora")):
        return "ORACLE"
    if any(k in n for k in ("crm", "dynamics", "salesforce", "d365")):
        return "CRM_API"
    if any(k in n for k in ("_api_", "rest", "http", "_api")):
        return "REST_API"
    if any(k in n for k in ("sql", "mssql", "sqlserver", "sqldb")):
        return "SQL_SERVER"
    return "OTHER"


def _detect_databricks_layer(job_name: str) -> str:
    """Infer the medallion layer from the Databricks job name."""
    n = job_name.lower()
    if any(k in n for k in ("bronze", "raw", "ingest", "landing", "stage")):
        return "BRONZE"
    if any(k in n for k in ("silver", "clean", "transform", "curated", "std")):
        return "SILVER"
    if any(k in n for k in ("gold", "mart", "agg", "aggregate", "report", "serving")):
        return "GOLD"
    return "OTHER"


def _truncate(s: str, max_len: int) -> str:
    return s[:max_len] + "..." if len(s) > max_len else s


def _get_secret(scope: str, key: str, env_fallback: str) -> str:
    import os
    try:
        from databricks.sdk.runtime import dbutils
        return dbutils.secrets.get(scope=scope, key=key)
    except Exception:
        return os.getenv(env_fallback, "")


# ═══════════════════════════════════════════════════════════════════════════
#  1. AZURE DATA FACTORY (ADF) MONITORING
# ═══════════════════════════════════════════════════════════════════════════

def _get_adf_client():
    """Return an authenticated ADF management client."""
    from azure.identity import DefaultAzureCredential
    from azure.mgmt.datafactory import DataFactoryManagementClient
    sub_id = _get_secret("coworker-agent", "azure-subscription-id", "AZURE_SUBSCRIPTION_ID")
    return DataFactoryManagementClient(DefaultAzureCredential(), sub_id)


def check_adf_pipeline_runs(
    resource_group: str,
    factory_name: str,
    hours_back: int = 24,
    status_filter: str = "Failed",
) -> str:
    """
    Query ADF pipeline runs filtered by status in the last N hours.
    Returns run ID, pipeline name, source type, error message, and duration.
    """
    try:
        from azure.mgmt.datafactory.models import RunFilterParameters, RunQueryFilter
        client = _get_adf_client()
    except ImportError:
        return json.dumps({"error": "Install: pip install azure-mgmt-datafactory azure-identity"})

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours_back)

    filters = RunFilterParameters(
        last_updated_after=start,
        last_updated_before=now,
        filters=[RunQueryFilter(operand="Status", operator="Equals", values=[status_filter])],
    )
    runs = client.pipeline_runs.query_by_factory(resource_group, factory_name, filters)

    results = []
    for run in runs.value:
        results.append({
            "run_id":        run.run_id,
            "pipeline_name": run.pipeline_name,
            "source_type":   _detect_adf_source_type(run.pipeline_name or ""),
            "status":        run.status,
            "start_time":    str(run.run_start),
            "end_time":      str(run.run_end),
            "duration_s":    run.duration_in_ms / 1000 if run.duration_in_ms else None,
            "error_message": _truncate(run.message or "", 500),
            "parameters":    run.parameters or {},
        })

    severity = "CRITICAL" if results else "OK"
    return json.dumps({
        "factory":       factory_name,
        "period_hours":  hours_back,
        "status_filter": status_filter,
        "failed_runs":   len(results),
        "severity":      severity,
        "runs":          results,
        "summary": (
            f"{'🔴' if results else '🟢'} "
            f"ADF '{factory_name}': {len(results)} {status_filter} pipeline(s) "
            f"in the last {hours_back}h."
        ),
    }, default=str)


def check_adf_by_source_type(
    resource_group: str,
    factory_name: str,
    hours_back: int = 24,
) -> str:
    """
    Group ALL ADF pipeline runs by source system type (SQL_SERVER, ORACLE,
    CRM_API, REST_API, OTHER) for the last N hours.

    Returns per-source counts of Succeeded / Failed / InProgress, so the agent
    can immediately see which ingestion channel is healthy and which is broken.
    This is the first call to make for any daily pipeline report.
    """
    try:
        from azure.mgmt.datafactory.models import RunFilterParameters
        client = _get_adf_client()
    except ImportError:
        return json.dumps({"error": "Install: pip install azure-mgmt-datafactory azure-identity"})

    now   = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours_back)

    # Fetch all runs (no status filter) so we can compute success rates
    filters = RunFilterParameters(last_updated_after=start, last_updated_before=now)
    runs = client.pipeline_runs.query_by_factory(resource_group, factory_name, filters)

    # Aggregate by source_type × status
    summary: dict[str, dict[str, int]] = {}
    failures: list[dict] = []

    for run in runs.value:
        src   = _detect_adf_source_type(run.pipeline_name or "")
        stat  = run.status or "Unknown"
        summary.setdefault(src, {"Succeeded": 0, "Failed": 0, "InProgress": 0, "Other": 0})

        bucket = stat if stat in ("Succeeded", "Failed", "InProgress") else "Other"
        summary[src][bucket] += 1

        if stat == "Failed":
            failures.append({
                "run_id":        run.run_id,
                "pipeline_name": run.pipeline_name,
                "source_type":   src,
                "error_message": _truncate(run.message or "", 400),
                "start_time":    str(run.run_start),
            })

    # Build per-source health
    source_health = {}
    overall_severity = "OK"
    for src, counts in summary.items():
        failed = counts["Failed"]
        total  = sum(counts.values())
        if failed > 0:
            sev = "CRITICAL" if failed >= total // 2 else "HIGH"
            overall_severity = "CRITICAL" if sev == "CRITICAL" else (
                "HIGH" if overall_severity != "CRITICAL" else overall_severity
            )
        else:
            sev = "OK"
        source_health[src] = {**counts, "total": total, "severity": sev}

    lines = []
    icons = {"OK": "🟢", "HIGH": "🟠", "CRITICAL": "🔴"}
    for src, h in source_health.items():
        lines.append(
            f"{icons[h['severity']]} {src:<12} "
            f"{h['Succeeded']} succeeded  "
            f"{h['Failed']} failed  "
            f"{h['InProgress']} running"
        )

    return json.dumps({
        "factory":          factory_name,
        "period_hours":     hours_back,
        "overall_severity": overall_severity,
        "by_source_type":   source_health,
        "failures":         failures,
        "summary_lines":    lines,
        "summary": (
            f"{'🔴' if overall_severity == 'CRITICAL' else '🟠' if overall_severity == 'HIGH' else '🟢'} "
            f"ADF source breakdown for last {hours_back}h:\n" + "\n".join(lines)
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

def _get_workspace_client():
    from databricks.sdk import WorkspaceClient
    return WorkspaceClient()


def check_databricks_job_runs(
    hours_back: int = 24,
    status_filter: str = "FAILED",
) -> str:
    """
    List recent Databricks workflow job runs, filtered by status.
    Returns run_id, job_id, run_name, layer, task-level errors.
    """
    try:
        w = _get_workspace_client()
    except ImportError:
        return json.dumps({"error": "databricks-sdk not available"})

    now      = datetime.now(timezone.utc)
    start_ms = int((now - timedelta(hours=hours_back)).timestamp() * 1000)
    runs     = list(w.jobs.list_runs(start_time_from=start_ms, expand_tasks=True, limit=100))

    results = []
    for run in runs:
        state = run.state
        if state and state.result_state and state.result_state.value == status_filter:
            task_errors = []
            for task in (run.tasks or []):
                ts = task.state
                if ts and ts.result_state and ts.result_state.value == "FAILED":
                    task_errors.append({
                        "task_key":      task.task_key,
                        "error_message": _truncate(ts.state_message or "", 400),
                        "notebook_path": getattr(task.notebook_task, "notebook_path", None) if task.notebook_task else None,
                    })
            results.append({
                "run_id":        run.run_id,
                "job_id":        run.job_id,
                "run_name":      run.run_name,
                "layer":         _detect_databricks_layer(run.run_name or ""),
                "start_time":    str(datetime.fromtimestamp(run.start_time / 1000, tz=timezone.utc)) if run.start_time else None,
                "state_message": _truncate(state.state_message or "", 400),
                "task_errors":   task_errors,
                "run_page_url":  run.run_page_url,
            })

    severity = "CRITICAL" if results else "OK"
    return json.dumps({
        "period_hours": hours_back,
        "status_filter": status_filter,
        "failed_runs":  len(results),
        "severity":     severity,
        "runs":         results,
        "summary": (
            f"{'🔴' if results else '🟢'} "
            f"Databricks: {len(results)} {status_filter} job run(s) in the last {hours_back}h."
        ),
    }, default=str)


def check_databricks_by_layer(hours_back: int = 24) -> str:
    """
    Group ALL Databricks job runs by medallion layer (BRONZE, SILVER, GOLD, OTHER)
    for the last N hours.

    Returns per-layer counts of Succeeded / Failed / Running and the list of
    failed jobs per layer, so the agent knows which transformation stage is
    broken and can assess the downstream cascade.
    """
    try:
        w = _get_workspace_client()
    except ImportError:
        return json.dumps({"error": "databricks-sdk not available"})

    now      = datetime.now(timezone.utc)
    start_ms = int((now - timedelta(hours=hours_back)).timestamp() * 1000)
    runs     = list(w.jobs.list_runs(start_time_from=start_ms, expand_tasks=True, limit=200))

    by_layer: dict[str, dict] = {}
    failures: list[dict]      = []

    for run in runs:
        state = run.state
        if not state:
            continue

        layer = _detect_databricks_layer(run.run_name or "")
        by_layer.setdefault(layer, {"SUCCEEDED": 0, "FAILED": 0, "RUNNING": 0, "OTHER": 0, "failed_jobs": []})

        if state.result_state:
            rs = state.result_state.value
            bucket = rs if rs in ("SUCCEEDED", "FAILED") else "OTHER"
        elif state.life_cycle_state and state.life_cycle_state.value == "RUNNING":
            bucket = "RUNNING"
        else:
            bucket = "OTHER"

        by_layer[layer][bucket] += 1

        if bucket == "FAILED":
            task_errors = []
            for task in (run.tasks or []):
                ts = task.state
                if ts and ts.result_state and ts.result_state.value == "FAILED":
                    task_errors.append({
                        "task_key":      task.task_key,
                        "error_message": _truncate(ts.state_message or "", 300),
                        "notebook_path": getattr(task.notebook_task, "notebook_path", None) if task.notebook_task else None,
                    })
            entry = {
                "run_id":        run.run_id,
                "job_id":        run.job_id,
                "run_name":      run.run_name,
                "layer":         layer,
                "state_message": _truncate(state.state_message or "", 300),
                "task_errors":   task_errors,
                "run_page_url":  run.run_page_url,
            }
            by_layer[layer]["failed_jobs"].append(entry)
            failures.append(entry)

    # Compute severity per layer
    overall_severity = "OK"
    layer_icons = {"OK": "🟢", "HIGH": "🟠", "CRITICAL": "🔴"}
    lines = []
    for layer in ["BRONZE", "SILVER", "GOLD", "OTHER"]:
        if layer not in by_layer:
            continue
        d = by_layer[layer]
        failed = d["FAILED"]
        total  = d["SUCCEEDED"] + d["FAILED"] + d["RUNNING"] + d["OTHER"]
        sev    = "CRITICAL" if failed > 0 and layer in ("BRONZE", "SILVER") else (
                 "HIGH" if failed > 0 else "OK")
        d["severity"] = sev
        d["total"]    = total
        if sev != "OK" and (overall_severity == "OK" or
           (overall_severity == "HIGH" and sev == "CRITICAL")):
            overall_severity = sev
        lines.append(
            f"{layer_icons[sev]} {layer:<8} "
            f"{d['SUCCEEDED']} succeeded  "
            f"{failed} failed  "
            f"{d['RUNNING']} running"
        )

    return json.dumps({
        "period_hours":     hours_back,
        "overall_severity": overall_severity,
        "by_layer":         by_layer,
        "all_failures":     failures,
        "summary_lines":    lines,
        "summary": (
            f"{'🔴' if overall_severity == 'CRITICAL' else '🟠' if overall_severity == 'HIGH' else '🟢'} "
            f"Databricks layer breakdown for last {hours_back}h:\n" + "\n".join(lines)
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
#  4. DAILY PIPELINE REPORT  (the main daily digest)
# ═══════════════════════════════════════════════════════════════════════════

def daily_pipeline_report(
    resource_group: str,
    factory_name: str,
    hours_back: int = 24,
    powerbi_workspace_id: str | None = None,
    powerbi_dataset_id:   str | None = None,
) -> str:
    """
    Generate a full end-to-end pipeline health report covering:
      1. ADF — breakdown by source type (SQL/Oracle/CRM/REST)
      2. Databricks — breakdown by layer (Bronze/Silver/Gold)
      3. Power BI — dataset refresh status
      4. LLM root-cause diagnosis for each failure
      5. Cascade impact map (which ADF failure blocked which layer)
      6. Auto-recovery actions attempted
      7. Overall health score + prioritised recommendations

    This is the single call the Pipeline Guardian skill makes for a daily
    health check or when asked "what failed today and why?".
    """
    report: dict[str, Any] = {
        "report_date":     datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "period_hours":    hours_back,
        "adf":             {},
        "databricks":      {},
        "powerbi":         {},
        "failure_details": [],
        "cascade_impacts": [],
        "recovery_actions": [],
        "recommendations": [],
        "overall_health":  "HEALTHY",
    }

    # ── Step 1: ADF by source type ────────────────────────────────────────
    try:
        adf_data = json.loads(check_adf_by_source_type(resource_group, factory_name, hours_back))
        report["adf"] = adf_data
    except Exception as exc:
        report["adf"] = {"error": str(exc)}

    # ── Step 2: Databricks by layer ───────────────────────────────────────
    try:
        db_data = json.loads(check_databricks_by_layer(hours_back))
        report["databricks"] = db_data
    except Exception as exc:
        report["databricks"] = {"error": str(exc)}

    # ── Step 3: Power BI ──────────────────────────────────────────────────
    if powerbi_workspace_id and powerbi_dataset_id:
        try:
            pbi_data = json.loads(check_powerbi_refresh_status(powerbi_workspace_id, powerbi_dataset_id))
            report["powerbi"] = pbi_data
        except Exception as exc:
            report["powerbi"] = {"error": str(exc)}

    # ── Step 4: Diagnose each ADF failure ─────────────────────────────────
    adf_failures = report["adf"].get("failures", [])
    for failure in adf_failures[:5]:   # cap at 5 to stay within context
        try:
            # Get activity-level errors for richer diagnosis
            activity_detail = ""
            try:
                acts = json.loads(get_adf_activity_errors(
                    resource_group, factory_name, failure["run_id"]
                ))
                for act in acts.get("errors", [])[:3]:
                    activity_detail += (
                        f"\nActivity '{act['activity_name']}' ({act['activity_type']}): "
                        f"{json.dumps(act.get('error', {}))[:400]}"
                    )
            except Exception:
                pass

            diagnosis = json.loads(diagnose_failure(
                error_message=failure["error_message"] + activity_detail,
                pipeline_type="ADF",
                pipeline_name=failure["pipeline_name"],
            ))
            detail = {
                "platform":      "ADF",
                "pipeline_name": failure["pipeline_name"],
                "source_type":   failure["source_type"],
                "run_id":        failure["run_id"],
                "error_summary": failure["error_message"],
                "diagnosis":     diagnosis,
            }
            report["failure_details"].append(detail)

            # Auto-recovery for transient failures
            if (diagnosis.get("auto_recovery_safe")
                    and diagnosis.get("recommended_action") == "RETRY"):
                try:
                    retry = json.loads(retry_adf_pipeline(
                        resource_group, factory_name, failure["pipeline_name"]
                    ))
                    report["recovery_actions"].append({
                        "action":   "RETRY_ADF",
                        "pipeline": failure["pipeline_name"],
                        "new_run":  retry.get("new_run_id"),
                        "result":   "Triggered",
                    })
                except Exception as exc:
                    report["recovery_actions"].append({
                        "action": "RETRY_ADF_FAILED",
                        "pipeline": failure["pipeline_name"],
                        "error": str(exc),
                    })
        except Exception as exc:
            log.warning("Could not diagnose ADF failure %s: %s", failure["pipeline_name"], exc)

    # ── Step 5: Diagnose each Databricks failure ──────────────────────────
    db_failures = report["databricks"].get("all_failures", [])
    for failure in db_failures[:5]:
        try:
            # Try to get notebook error trace
            error_text = failure.get("state_message", "")
            for te in failure.get("task_errors", []):
                error_text += f"\nTask '{te['task_key']}': {te['error_message']}"
                if te.get("notebook_path"):
                    error_text += f" [notebook: {te['notebook_path']}]"

            diagnosis = json.loads(diagnose_failure(
                error_message=error_text,
                pipeline_type="Databricks",
                pipeline_name=failure.get("run_name", ""),
                notebook_path=failure.get("task_errors", [{}])[0].get("notebook_path") if failure.get("task_errors") else None,
            ))
            detail = {
                "platform":   "Databricks",
                "run_name":   failure.get("run_name"),
                "layer":      failure.get("layer"),
                "run_id":     failure.get("run_id"),
                "job_id":     failure.get("job_id"),
                "task_errors": failure.get("task_errors", []),
                "diagnosis":  diagnosis,
            }
            report["failure_details"].append(detail)

            # Auto-recovery for transient Databricks failures
            if (diagnosis.get("auto_recovery_safe")
                    and diagnosis.get("recommended_action") == "RETRY"
                    and failure.get("job_id")):
                try:
                    retry = json.loads(retry_databricks_job(job_id=failure["job_id"]))
                    report["recovery_actions"].append({
                        "action":  "RETRY_DATABRICKS",
                        "job":     failure.get("run_name"),
                        "new_run": retry.get("new_run_id"),
                        "result":  "Triggered",
                    })
                except Exception as exc:
                    report["recovery_actions"].append({
                        "action": "RETRY_DATABRICKS_FAILED",
                        "job": failure.get("run_name"),
                        "error": str(exc),
                    })
        except Exception as exc:
            log.warning("Could not diagnose Databricks failure %s: %s", failure.get("run_name"), exc)

    # ── Step 6: Build cascade impact map ─────────────────────────────────
    # Match ADF pipeline name keywords to Databricks job names
    for adf_fail in adf_failures:
        adf_keywords = set(re.findall(r"\w+", adf_fail["pipeline_name"].lower()))
        adf_keywords -= {"adf", "pipeline", "copy", "ingest", "load", "run", "the", "and"}
        impacted_jobs = []
        for db_fail in db_failures:
            db_keywords = set(re.findall(r"\w+", db_fail.get("run_name", "").lower()))
            if adf_keywords & db_keywords:
                impacted_jobs.append({
                    "job_name": db_fail.get("run_name"),
                    "layer":    db_fail.get("layer"),
                })
        if impacted_jobs:
            report["cascade_impacts"].append({
                "root_cause": f"ADF: {adf_fail['pipeline_name']} ({adf_fail['source_type']})",
                "downstream": impacted_jobs,
                "description": (
                    f"ADF pipeline '{adf_fail['pipeline_name']}' failed to ingest from "
                    f"{adf_fail['source_type']}. This has blocked "
                    f"{len(impacted_jobs)} downstream Databricks job(s): "
                    f"{', '.join(j['job_name'] for j in impacted_jobs)}."
                ),
            })

    # ── Step 7: Overall health + recommendations ──────────────────────────
    adf_sev = report["adf"].get("overall_severity", "OK")
    db_sev  = report["databricks"].get("overall_severity", "OK")
    pbi_sev = report["powerbi"].get("severity", "OK")
    sev_rank = {"OK": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    worst = max(adf_sev, db_sev, pbi_sev, key=lambda s: sev_rank.get(s, 0))
    report["overall_health"] = (
        "CRITICAL" if worst == "CRITICAL" else
        "DEGRADED"  if worst in ("HIGH", "MEDIUM") else
        "HEALTHY"
    )

    for detail in report["failure_details"]:
        d = detail.get("diagnosis", {})
        if d.get("recommended_action") not in (None, "RETRY"):
            report["recommendations"].append({
                "priority": d.get("urgency", "MEDIUM"),
                "pipeline": detail.get("pipeline_name") or detail.get("run_name"),
                "action":   d.get("recommended_action"),
                "reason":   d.get("root_cause_explanation", ""),
                "fix":      d.get("auto_recovery_steps", []),
            })

    # Overall narrative
    health_icon = {"HEALTHY": "🟢", "DEGRADED": "🟠", "CRITICAL": "🔴"}[report["overall_health"]]
    report["executive_summary"] = (
        f"{health_icon} Pipeline Health: {report['overall_health']} "
        f"({len(adf_failures)} ADF failure(s), "
        f"{len(db_failures)} Databricks failure(s), "
        f"{len(report['cascade_impacts'])} cascade impact(s), "
        f"{len(report['recovery_actions'])} auto-recovery action(s) taken)"
    )

    return json.dumps(report, default=str)


def get_pipeline_cascade_impact(
    failed_pipeline_name: str,
    resource_group: str,
    factory_name: str,
    hours_back: int = 24,
) -> str:
    """
    Given the name of a failed ADF pipeline, trace the full downstream blast
    radius through the medallion layers to Power BI.

    How it works:
      1. Identifies the source type (SQL/Oracle/CRM/REST) from the pipeline name
      2. Searches recent Databricks failures for jobs with matching name keywords
      3. Groups impacted jobs by layer (Bronze → Silver → Gold)
      4. Assesses whether Power BI datasets are affected
      5. Returns a human-readable cascade description with business impact

    Use this when a user asks: "If X ADF pipeline failed, what else broke?"
    """
    try:
        w = _get_workspace_client()
    except ImportError:
        return json.dumps({"error": "databricks-sdk not available"})

    src_type = _detect_adf_source_type(failed_pipeline_name)
    adf_keywords = set(re.findall(r"\w+", failed_pipeline_name.lower()))
    adf_keywords -= {"adf", "pipeline", "copy", "ingest", "load", "run", "the", "and", "data"}

    now      = datetime.now(timezone.utc)
    start_ms = int((now - timedelta(hours=hours_back)).timestamp() * 1000)
    runs     = list(w.jobs.list_runs(start_time_from=start_ms, expand_tasks=True, limit=100))

    # Find Databricks jobs that likely depend on this ADF pipeline
    impacted: dict[str, list] = {"BRONZE": [], "SILVER": [], "GOLD": [], "OTHER": []}
    for run in runs:
        job_keywords = set(re.findall(r"\w+", (run.run_name or "").lower()))
        if adf_keywords & job_keywords:
            layer = _detect_databricks_layer(run.run_name or "")
            state  = run.state
            status = "UNKNOWN"
            if state and state.result_state:
                status = state.result_state.value
            elif state and state.life_cycle_state:
                status = state.life_cycle_state.value
            impacted[layer].append({
                "job_name":  run.run_name,
                "run_id":    run.run_id,
                "status":    status,
                "page_url":  run.run_page_url,
            })

    # Build narrative
    layers_affected = [l for l, jobs in impacted.items() if jobs and l != "OTHER"]
    business_impact = _cascade_business_impact(failed_pipeline_name, src_type, layers_affected)

    cascade_lines = [f"🔴 ADF FAILURE: {failed_pipeline_name} ({src_type})"]
    for layer in ["BRONZE", "SILVER", "GOLD"]:
        if impacted[layer]:
            icons = {"BRONZE": "🟫", "SILVER": "🔘", "GOLD": "🟡"}
            for j in impacted[layer]:
                status_icon = "🔴" if j["status"] == "FAILED" else "🟡" if j["status"] in ("RUNNING", "PENDING") else "✅"
                cascade_lines.append(f"  {icons[layer]} {layer}: {j['job_name']} [{status_icon} {j['status']}]")

    return json.dumps({
        "failed_adf_pipeline":     failed_pipeline_name,
        "source_type":             src_type,
        "layers_affected":         layers_affected,
        "impacted_jobs_by_layer":  impacted,
        "cascade_description":     "\n".join(cascade_lines),
        "business_impact":         business_impact,
        "severity": (
            "CRITICAL" if "BRONZE" in layers_affected else
            "HIGH"     if "SILVER" in layers_affected else
            "MEDIUM"   if layers_affected else "LOW"
        ),
    }, default=str)


def _cascade_business_impact(pipeline_name: str, src_type: str, layers: list[str]) -> str:
    """Generate a plain-language business impact statement."""
    n = pipeline_name.lower()
    subject = (
        "attendance data" if "attendance" in n or "attn" in n else
        "revenue data"    if "revenue" in n or "rev" in n else
        "sales data"      if "sales" in n or "sal" in n else
        "CRM data"        if src_type == "CRM_API" else
        f"{src_type} data"
    )
    if "GOLD" in layers:
        return (
            f"All three transformation layers are affected. {subject.capitalize()} "
            "will not reach Power BI dashboards. Reports will show stale figures."
        )
    if "SILVER" in layers:
        return (
            f"{subject.capitalize()} has reached Bronze but failed to clean/transform. "
            "Gold aggregations and Power BI will use yesterday's data."
        )
    if "BRONZE" in layers:
        return (
            f"{subject.capitalize()} failed to land from the Landing Zone into Bronze. "
            "All downstream layers (Silver, Gold, Power BI) are blocked."
        )
    return f"{subject.capitalize()} may be affected. Check downstream jobs manually."


# ═══════════════════════════════════════════════════════════════════════════
#  5. POST-LOAD VALIDATION
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
    # ── New architecture-aware tools ──────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "daily_pipeline_report",
            "description": (
                "Generate the full end-to-end daily pipeline health report. "
                "Covers ADF (by source type: SQL/Oracle/CRM/REST), Databricks "
                "(by layer: Bronze/Silver/Gold), and Power BI in one call. "
                "Diagnoses every failure, maps cascade impacts, attempts "
                "auto-recovery, and returns an executive summary + recommendations. "
                "Use this for 'what failed today?', 'give me the daily report', "
                "'how are our pipelines?'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "resource_group":        {"type": "string", "description": "Azure resource group containing ADF"},
                    "factory_name":          {"type": "string", "description": "ADF instance name"},
                    "hours_back":            {"type": "integer", "default": 24, "description": "Hours to look back (24 = daily)"},
                    "powerbi_workspace_id":  {"type": "string", "description": "Power BI workspace ID (optional)"},
                    "powerbi_dataset_id":    {"type": "string", "description": "Power BI dataset ID (optional)"},
                },
                "required": ["resource_group", "factory_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_adf_by_source_type",
            "description": (
                "Group ALL ADF pipeline runs by source system: SQL_SERVER, ORACLE, "
                "CRM_API, REST_API, OTHER. Returns per-source success/failure counts "
                "so you can instantly see which ingestion channel is broken."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "resource_group": {"type": "string"},
                    "factory_name":   {"type": "string"},
                    "hours_back":     {"type": "integer", "default": 24},
                },
                "required": ["resource_group", "factory_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_databricks_by_layer",
            "description": (
                "Group ALL Databricks job runs by medallion layer: BRONZE, SILVER, GOLD. "
                "Returns per-layer success/failure counts and the list of failed jobs "
                "so you can see which transformation stage is broken."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hours_back": {"type": "integer", "default": 24},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pipeline_cascade_impact",
            "description": (
                "Trace the full downstream blast radius of a failed ADF pipeline: "
                "which Bronze/Silver/Gold Databricks jobs are blocked, and what is "
                "the business impact on dashboards and reports. "
                "Use when: 'if oracle_attendance failed, what else broke?'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "failed_pipeline_name": {"type": "string", "description": "Name of the failed ADF pipeline"},
                    "resource_group":       {"type": "string"},
                    "factory_name":         {"type": "string"},
                    "hours_back":           {"type": "integer", "default": 24},
                },
                "required": ["failed_pipeline_name", "resource_group", "factory_name"],
            },
        },
    },
    # ── Core ADF tools ────────────────────────────────────────────────────
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
        # Architecture-aware (new)
        "daily_pipeline_report":         daily_pipeline_report,
        "check_adf_by_source_type":      check_adf_by_source_type,
        "check_databricks_by_layer":     check_databricks_by_layer,
        "get_pipeline_cascade_impact":   get_pipeline_cascade_impact,
        # Core ADF
        "check_adf_pipeline_runs":       check_adf_pipeline_runs,
        "get_adf_activity_errors":       get_adf_activity_errors,
        "retry_adf_pipeline":            retry_adf_pipeline,
        # Core Databricks
        "check_databricks_job_runs":     check_databricks_job_runs,
        "get_databricks_job_run_output": get_databricks_job_run_output,
        "retry_databricks_job":          retry_databricks_job,
        # Power BI
        "check_powerbi_refresh_status":  check_powerbi_refresh_status,
        "trigger_powerbi_refresh":       trigger_powerbi_refresh,
        # Validation + Diagnosis
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
