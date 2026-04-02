# Databricks notebook source
# MAGIC %md
# MAGIC # Pipeline Guardian — Daily Monitoring Notebook
# MAGIC
# MAGIC End-to-end pipeline health checks for the Yas Entertainment data platform.
# MAGIC
# MAGIC **Architecture monitored:**
# MAGIC ```
# MAGIC ADF (SQL / Oracle / CRM API / REST API)
# MAGIC   → Landing Zone (ADLS)
# MAGIC     → Databricks Bronze  →  Silver  →  Gold
# MAGIC                                           → Power BI
# MAGIC ```
# MAGIC
# MAGIC **Run this notebook:**
# MAGIC - Manually: open and run all cells
# MAGIC - Scheduled: attach to the `proactive_monitor` Databricks job (runs every 30 min)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Setup

# COMMAND ----------

import sys, os, json
from pathlib import Path

repo_root = os.path.dirname(os.path.dirname(
    dbutils.notebook.entry_point.getDbutils().notebook().getContext()
    .extraContext().apply("notebook_path")
))
sys.path.insert(0, f"/Workspace{repo_root}")

# Your ADF configuration — update these or set as widgets
ADF_RESOURCE_GROUP = dbutils.widgets.get("ADF_RESOURCE_GROUP") if dbutils.widgets.getAll() else "rg-miral-data"
ADF_FACTORY_NAME   = dbutils.widgets.get("ADF_FACTORY_NAME")   if dbutils.widgets.getAll() else "miral-adf-prod"
PBI_WORKSPACE_ID   = dbutils.widgets.get("POWERBI_WORKSPACE_ID") if dbutils.widgets.getAll() else ""
PBI_DATASET_ID     = dbutils.widgets.get("POWERBI_DATASET_ID")   if dbutils.widgets.getAll() else ""

from src.coworker.agent import CoworkerAgent

print("Pipeline Guardian loaded.")
print(f"Monitoring ADF: {ADF_FACTORY_NAME} in {ADF_RESOURCE_GROUP}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Daily Pipeline Report
# MAGIC
# MAGIC One command — full end-to-end report covering ADF, Bronze, Silver, Gold, Power BI.

# COMMAND ----------

agent = CoworkerAgent(conversation_id="pipeline-guardian-daily")

report = agent.handle_message(
    f"Generate the daily pipeline report for ADF factory '{ADF_FACTORY_NAME}' "
    f"in resource group '{ADF_RESOURCE_GROUP}' for the last 24 hours. "
    + (f"Also check Power BI workspace {PBI_WORKSPACE_ID} dataset {PBI_DATASET_ID}." if PBI_WORKSPACE_ID else "")
)

print(report)
print(f"\n[Skill: {agent.active_skill}]")

# COMMAND ----------

# MAGIC %md
# MAGIC ## ADF Failures by Source Type
# MAGIC
# MAGIC Which ingestion channel is broken — SQL Server, Oracle, CRM API, or REST API?

# COMMAND ----------

reply = agent.handle_message(
    f"Break down all ADF pipeline failures in the last 24 hours by source type "
    f"(SQL Server, Oracle, CRM API, REST API). "
    f"Factory: '{ADF_FACTORY_NAME}', resource group: '{ADF_RESOURCE_GROUP}'."
)
print(reply)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Databricks Layer Health
# MAGIC
# MAGIC Which medallion layer (Bronze / Silver / Gold) has failing jobs?

# COMMAND ----------

reply = agent.handle_message(
    "Show me the Databricks job health broken down by Bronze, Silver, and Gold layers "
    "for the last 24 hours. Which layer is failing and what are the job names?"
)
print(reply)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cascade Impact Analysis
# MAGIC
# MAGIC If an ADF pipeline failed, what Databricks layers and Power BI reports are blocked?
# MAGIC Change the pipeline name below to the one you want to investigate.

# COMMAND ----------

# Replace with the name of the failed pipeline you want to trace
FAILED_PIPELINE = "oracle_attendance_ingest"   # ← change me

reply = agent.handle_message(
    f"The ADF pipeline '{FAILED_PIPELINE}' failed. "
    f"Trace the full cascade impact: which Bronze/Silver/Gold Databricks jobs are blocked? "
    f"What is the business impact on dashboards? "
    f"Factory: '{ADF_FACTORY_NAME}', resource group: '{ADF_RESOURCE_GROUP}'."
)
print(reply)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Diagnose a Specific Pipeline Failure
# MAGIC
# MAGIC Paste the error message from a failed pipeline run to get a root-cause diagnosis.

# COMMAND ----------

ERROR_MESSAGE = """
ErrorCode: UserErrorOdbcSourceError
Message: ODBC Source encountered error. ErrorMessage: [Oracle][ODBC Oracle Wire Protocol driver]
Timeout expired. The timeout period elapsed prior to completion of the operation or the server is not responding.
Pipeline: oracle_attendance_load
Activity: CopyFromOracleToLanding
Duration: 3601 seconds
"""

reply = agent.handle_message(
    f"Diagnose this pipeline failure and tell me: "
    f"1) Root cause category  "
    f"2) Is auto-recovery safe?  "
    f"3) Exact fix steps  "
    f"4) Business impact\n\nError:\n{ERROR_MESSAGE}"
)
print(reply)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Manual Retry
# MAGIC
# MAGIC After the agent diagnoses a failure as transient (timeout / network),
# MAGIC it will auto-retry.  Use this cell to force-retry a specific pipeline.

# COMMAND ----------

# Only run this after the agent confirms the failure is safe to retry
reply = agent.handle_message(
    f"Retry the ADF pipeline 'oracle_attendance_load' in factory '{ADF_FACTORY_NAME}', "
    f"resource group '{ADF_RESOURCE_GROUP}'. "
    "Only retry if the root cause is transient (timeout or network issue)."
)
print(reply)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Post-Load Validation
# MAGIC
# MAGIC After a pipeline recovers, validate that data actually landed correctly.

# COMMAND ----------

reply = agent.handle_message(
    "Run post-load validation on all three monitored tables: "
    "park_ops.tbvw_attendance, "
    "park_ops.tbvw_sales_transactions, "
    "park_ops.tbvw_daily_revenue_data_ss. "
    "Check row counts, today's partition, and key column null rates."
)
print(reply)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Save Report to Knowledge Base

# COMMAND ----------

reply = agent.handle_message(
    "Save today's pipeline health findings to the knowledge base as a daily incident report. "
    "Include the failures found, root causes, cascade impacts, and any actions taken."
)
print(reply)
