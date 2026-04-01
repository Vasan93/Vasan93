"""
Proactive Monitor — Databricks Scheduled Job
=============================================
Runs on a schedule (e.g. every 30 minutes) to:

  1. Check ADF pipeline runs for failures → diagnose → auto-recover if safe
  2. Check Databricks workflow runs for failures → diagnose → auto-recover
  3. Check Power BI dataset refresh status
  4. After any successful load, validate data (row count, nulls, freshness)
  5. Send a consolidated Teams alert (Adaptive Card) with all findings

Schedule this as a Databricks Workflow job:
  Cluster: any shared cluster with the coworker package installed
  Schedule: every 30 minutes during business hours (or 24/7 for critical tables)
  Alerts: on failure → ops team email

Configuration is read from Databricks Secret Scopes (see config.py).
Override monitored tables / ADF factory etc. via environment variables or
widget parameters.
"""

import json
import logging
import asyncio
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("proactive_monitor")


def main():
    from src.coworker.config import cfg
    from src.coworker.tools.data_quality import full_table_health
    from src.coworker.tools.pipeline_monitor import (
        check_adf_pipeline_runs,
        check_databricks_job_runs,
        check_powerbi_refresh_status,
        validate_post_load,
        diagnose_failure,
        retry_adf_pipeline,
        retry_databricks_job,
        trigger_powerbi_refresh,
    )
    from app.teams_handler import TeamsBotHandler

    findings: list[dict] = []
    recovery_actions: list[str] = []
    now = datetime.now(timezone.utc)
    log.info("=== Proactive Monitor Run: %s ===", now.isoformat())

    # ── 1. Databricks workflow failures ───────────────────────────────────
    log.info("Checking Databricks workflow runs...")
    try:
        db_result = json.loads(check_databricks_job_runs(hours_back=1, status_filter="FAILED"))
        if db_result.get("failed_runs", 0) > 0:
            findings.append({
                "source": "Databricks Workflows",
                "severity": "CRITICAL",
                "detail": db_result["summary"],
                "runs": db_result.get("runs", []),
            })

            # Diagnose each failure and attempt auto-recovery
            for run in db_result.get("runs", [])[:5]:
                error_msg = run.get("state_message", "")
                for te in run.get("task_errors", []):
                    error_msg += f"\nTask '{te['task_key']}': {te['error_message']}"

                diagnosis = json.loads(diagnose_failure(
                    error_message=error_msg,
                    pipeline_type="Databricks",
                    pipeline_name=run.get("run_name", ""),
                ))

                if diagnosis.get("auto_recovery_safe") and diagnosis.get("recommended_action") == "RETRY":
                    log.info("Auto-recovering Databricks job %s...", run.get("job_id"))
                    retry_result = json.loads(retry_databricks_job(job_id=run["job_id"]))
                    recovery_actions.append(
                        f"Retried Databricks job {run['job_id']} → run {retry_result.get('new_run_id')}"
                    )
                else:
                    findings[-1]["diagnosis"] = diagnosis
        else:
            log.info("No Databricks failures found.")
    except Exception as exc:
        log.warning("Databricks check failed: %s", exc)

    # ── 2. ADF pipeline failures ──────────────────────────────────────────
    adf_rg = _get_param("ADF_RESOURCE_GROUP")
    adf_factory = _get_param("ADF_FACTORY_NAME")
    if adf_rg and adf_factory:
        log.info("Checking ADF pipelines...")
        try:
            adf_result = json.loads(check_adf_pipeline_runs(
                resource_group=adf_rg,
                factory_name=adf_factory,
                hours_back=1,
            ))
            if adf_result.get("failed_runs", 0) > 0:
                findings.append({
                    "source": "Azure Data Factory",
                    "severity": "CRITICAL",
                    "detail": adf_result["summary"],
                    "runs": adf_result.get("runs", []),
                })

                for run in adf_result.get("runs", [])[:5]:
                    diagnosis = json.loads(diagnose_failure(
                        error_message=run.get("error_message", ""),
                        pipeline_type="ADF",
                        pipeline_name=run.get("pipeline_name", ""),
                    ))
                    if diagnosis.get("auto_recovery_safe") and diagnosis.get("recommended_action") == "RETRY":
                        log.info("Auto-recovering ADF pipeline %s...", run.get("pipeline_name"))
                        retry_result = json.loads(retry_adf_pipeline(
                            resource_group=adf_rg,
                            factory_name=adf_factory,
                            pipeline_name=run["pipeline_name"],
                            parameters=run.get("parameters"),
                        ))
                        recovery_actions.append(
                            f"Retried ADF pipeline '{run['pipeline_name']}' → run {retry_result.get('new_run_id')}"
                        )
            else:
                log.info("No ADF failures found.")
        except Exception as exc:
            log.warning("ADF check failed: %s", exc)

    # ── 3. Power BI refresh status ────────────────────────────────────────
    pbi_ws = _get_param("POWERBI_WORKSPACE_ID")
    pbi_ds = _get_param("POWERBI_DATASET_ID")
    if pbi_ws and pbi_ds:
        log.info("Checking Power BI refresh...")
        try:
            pbi_result = json.loads(check_powerbi_refresh_status(
                workspace_id=pbi_ws, dataset_id=pbi_ds,
            ))
            if pbi_result.get("severity") == "CRITICAL":
                findings.append({
                    "source": "Power BI",
                    "severity": "CRITICAL",
                    "detail": pbi_result["summary"],
                })
                # Trigger refresh after upstream is confirmed OK
                if not any(f["source"] in ("ADF", "Databricks Workflows") and f["severity"] == "CRITICAL"
                           for f in findings):
                    log.info("Upstream OK — triggering Power BI refresh...")
                    trigger_powerbi_refresh(workspace_id=pbi_ws, dataset_id=pbi_ds)
                    recovery_actions.append("Triggered Power BI dataset refresh (upstream loads OK).")
            else:
                log.info("Power BI refresh OK.")
        except Exception as exc:
            log.warning("Power BI check failed: %s", exc)

    # ── 4. Post-load data validation ──────────────────────────────────────
    log.info("Running post-load validation on monitored tables...")
    for table in cfg.MONITORED_TABLES:
        try:
            health = json.loads(full_table_health(table))
            if health.get("overall_severity") in ("CRITICAL", "HIGH"):
                findings.append({
                    "source": f"Data Quality: {table}",
                    "severity": health["overall_severity"],
                    "detail": (
                        f"Freshness: {health['freshness'].get('summary', 'N/A')}\n"
                        f"Row count: {health['row_count_check'].get('summary', 'N/A')}"
                    ),
                })

            # Run full post-load validation
            validation = json.loads(validate_post_load(table))
            if not validation.get("overall_passed"):
                findings.append({
                    "source": f"Post-Load Validation: {table}",
                    "severity": validation.get("overall_severity", "HIGH"),
                    "detail": validation["summary"],
                    "checks": validation.get("checks"),
                })
            else:
                log.info("Post-load OK: %s", table)
        except Exception as exc:
            log.warning("Validation failed for %s: %s", table, exc)

    # ── 5. Send Teams alert ───────────────────────────────────────────────
    if findings:
        alert_title = f"🚨 Co-Worker Alert — {len(findings)} issue(s) detected"
        alert_lines = []
        for f in findings:
            icon = "🔴" if f["severity"] == "CRITICAL" else "🟠"
            alert_lines.append(f"{icon} **{f['source']}** [{f['severity']}]\n{f['detail']}")

        if recovery_actions:
            alert_lines.append("\n**Auto-Recovery Actions Taken:**")
            for a in recovery_actions:
                alert_lines.append(f"✅ {a}")

        alert_body = "\n\n".join(alert_lines)

        log.info("Sending Teams alert: %d finding(s), %d recovery action(s)",
                 len(findings), len(recovery_actions))

        if cfg.ALERT_WEBHOOK_URL:
            asyncio.run(TeamsBotHandler.send_alert_to_webhook(
                cfg.ALERT_WEBHOOK_URL, alert_title, alert_body,
            ))
        else:
            log.warning("ALERT_WEBHOOK_URL not configured — printing alert to stdout.")
            print(f"\n{alert_title}\n{'=' * 60}\n{alert_body}")
    else:
        log.info("All systems healthy. No alerts to send.")

    log.info("=== Proactive Monitor Complete ===")
    return {"findings": len(findings), "recoveries": len(recovery_actions)}


def _get_param(name: str) -> str:
    """Read from Databricks widget parameters, falling back to env vars."""
    import os
    try:
        from databricks.sdk.runtime import dbutils
        return dbutils.widgets.get(name)
    except Exception:
        return os.getenv(name, "")


if __name__ == "__main__":
    main()
