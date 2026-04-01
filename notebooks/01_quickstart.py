# Databricks notebook source
# MAGIC %md
# MAGIC # Co-Worker Agent — Quickstart
# MAGIC
# MAGIC Interactive notebook to talk to the Co-Worker Agent directly from Databricks.
# MAGIC
# MAGIC **Prerequisites:**
# MAGIC 1. Cluster has the `coworker-agent` package installed (`pip install -e /Workspace/Repos/<your-path>`)
# MAGIC 2. Databricks Secret Scope `coworker-agent` configured with:
# MAGIC    - `ai-foundry-endpoint` — Azure AI Foundry project endpoint
# MAGIC    - `ai-foundry-key` — API key
# MAGIC 3. Unity Catalog `miral_coworker.agent_state` schema created

# COMMAND ----------

# MAGIC %md
# MAGIC ## Setup — run once per session

# COMMAND ----------

import sys, os

# Add repo root to path (adjust to your workspace path)
repo_root = os.path.dirname(os.path.dirname(dbutils.notebook.entry_point.getDbutils().notebook().getContext().extraContext().apply("notebook_path")))
sys.path.insert(0, f"/Workspace{repo_root}")

from src.coworker.agent import CoworkerAgent, ask

print("Co-Worker Agent loaded successfully!")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Quick one-liner — ask anything

# COMMAND ----------

# Just ask a question — the agent will use its tools automatically
ask("What data quality issues should I know about in the ATTENDANCE table?")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Interactive conversation — multi-turn

# COMMAND ----------

# Start a conversation (state is preserved across calls)
agent = CoworkerAgent(conversation_id="notebook-demo")

# COMMAND ----------

# Turn 1: Ask about the business
print(agent.handle_message(
    "I'm a new data engineer. Give me a quick overview of the parks business and the data warehouse."
))

# COMMAND ----------

# Turn 2: The agent remembers context from Turn 1
print(agent.handle_message(
    "Which tables should I focus on first, and what are the known issues?"
))

# COMMAND ----------

# Turn 3: Ask it to check live data
print(agent.handle_message(
    "Check the health of all three monitored tables right now."
))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Pipeline Monitoring — check for failures

# COMMAND ----------

print(agent.handle_message(
    "Check if any Databricks jobs have failed in the last 6 hours. "
    "If you find failures, diagnose the root cause and tell me if auto-recovery is safe."
))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Data Quality Audit

# COMMAND ----------

print(agent.handle_message(
    "Run a comprehensive data quality audit: "
    "check row-count anomalies, null rates on key columns, and cross-table "
    "type consistency for Voucher ID and B2B Account ID. "
    "Save the findings to the knowledge base."
))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Onboarding — get a learning plan

# COMMAND ----------

print(agent.handle_message("Give me the full onboarding plan for a new data engineer."))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Business Glossary

# COMMAND ----------

print(agent.handle_message("What does RPV mean? And what about DMG and OMNI Pass?"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Knowledge Base — search and browse

# COMMAND ----------

print(agent.handle_message("Search the knowledge base for articles about data quality."))

# COMMAND ----------

print(agent.handle_message("List all articles in the knowledge base."))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Code Navigation — explore the warehouse

# COMMAND ----------

print(agent.handle_message(
    "Search the data warehouse for all columns that contain 'voucher' in their name. "
    "Which tables have them and what are the data types?"
))

# COMMAND ----------

print(agent.handle_message(
    "Describe the full schema of park_ops.tbvw_attendance and tell me "
    "which columns are most important for the daily attendance dashboard."
))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Custom SQL Investigation

# COMMAND ----------

print(agent.handle_message(
    "Run a SQL query to check if there are any Voucher IDs in the SALES table "
    "that don't exist in the ATTENDANCE table. Show me the count and a few examples."
))
