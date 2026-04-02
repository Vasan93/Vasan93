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
# MAGIC ## Skills Overview
# MAGIC
# MAGIC The agent uses **8 specialised skills**. Each skill has its own focused tools and instructions.
# MAGIC When you send a message, the agent automatically routes it to the best skill.

# COMMAND ----------

# List all registered skills
agent = CoworkerAgent(conversation_id="notebook-skills-demo")
for skill in agent.list_skills():
    print(f"  {skill['name']:<22} | {skill['tool_count']} tools | {skill['description'][:60]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Skill 1 — Pipeline Guardian
# MAGIC Monitors ADF, Databricks jobs, and Power BI refreshes.

# COMMAND ----------

agent_pg = CoworkerAgent(conversation_id="demo-pipeline")
reply = agent_pg.handle_message(
    "Check if any Databricks jobs have failed in the last 6 hours. "
    "If failures exist, diagnose root cause and tell me if auto-recovery is safe."
)
print(f"[Skill activated: {agent_pg.active_skill}]\n")
print(reply)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Skill 2 — Data Detective
# MAGIC Proactively finds anomalies, null rates, type mismatches, and join issues.

# COMMAND ----------

agent_dd = CoworkerAgent(conversation_id="demo-detective")
reply = agent_dd.handle_message(
    "Run a proactive data quality audit. Check row-count anomalies and null rates "
    "on key ID columns across the three warehouse views."
)
print(f"[Skill activated: {agent_dd.active_skill}]\n")
print(reply)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Skill 3 — Post-Load Validator
# MAGIC Validates data after ETL: row counts, date partitions, null rates, cross-table consistency.

# COMMAND ----------

agent_plv = CoworkerAgent(conversation_id="demo-validator")
reply = agent_plv.handle_message(
    "Validate that today's ETL loaded correctly. Check row counts, "
    "confirm today's date partition exists, and verify key columns have acceptable null rates."
)
print(f"[Skill activated: {agent_plv.active_skill}]\n")
print(reply)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Skill 4 — Schema Explorer
# MAGIC Navigates table schemas, searches columns by name, and traces data lineage.

# COMMAND ----------

agent_se = CoworkerAgent(conversation_id="demo-schema")
reply = agent_se.handle_message(
    "Search the data warehouse for all columns that contain 'voucher' in their name. "
    "Which tables have them and what are the data types? Are there any type mismatches?"
)
print(f"[Skill activated: {agent_se.active_skill}]\n")
print(reply)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Skill 5 — Code Explainer
# MAGIC Reads and explains Databricks notebooks, ETL logic, and SQL transformations.

# COMMAND ----------

agent_ce = CoworkerAgent(conversation_id="demo-code")
reply = agent_ce.handle_message(
    "Describe the full schema of park_ops.tbvw_attendance and explain "
    "which columns are most important for the daily attendance dashboard."
)
print(f"[Skill activated: {agent_ce.active_skill}]\n")
print(reply)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Skill 6 — Onboarding Coach
# MAGIC Produces structured onboarding plans, explains business concepts, and defines glossary terms.

# COMMAND ----------

agent_oc = CoworkerAgent(conversation_id="demo-onboarding")
reply = agent_oc.handle_message(
    "I'm a new data engineer. Give me the full onboarding plan for my role."
)
print(f"[Skill activated: {agent_oc.active_skill}]\n")
print(reply)

# COMMAND ----------

reply = agent_oc.handle_message(
    "What does RPV mean? Also explain DMG, OMNI Pass, and Pax in plain language."
)
print(reply)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Skill 7 — Knowledge Manager
# MAGIC Saves, searches, and retrieves knowledge-base articles.

# COMMAND ----------

agent_km = CoworkerAgent(conversation_id="demo-kb")
reply = agent_km.handle_message(
    "Search the knowledge base for articles about data quality and type mismatches."
)
print(f"[Skill activated: {agent_km.active_skill}]\n")
print(reply)

# COMMAND ----------

# Save a new article
reply = agent_km.handle_message(
    "Save this to the knowledge base: "
    "Title: 'Voucher ID Type Mismatch'. "
    "Category: data_quality. "
    "Content: The Voucher ID column is stored as NUMBER(38,0) in ATTENDANCE and REVENUE "
    "but as TEXT in SALES. This causes JOIN failures between SAL and ATT. "
    "Fix: CAST(sal.voucher_id AS NUMBER) in any cross-table query. "
    "Tags: voucher, type-mismatch, join, sales, attendance."
)
print(reply)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Skill 8 — Incident Responder
# MAGIC End-to-end incident triage: report → data → pipeline → root cause.

# COMMAND ----------

agent_ir = CoworkerAgent(conversation_id="demo-incident")
reply = agent_ir.handle_message(
    "The morning attendance report shows zero records for yesterday. "
    "Triage this incident end-to-end: check the pipeline, the data, and give me a root cause."
)
print(f"[Skill activated: {agent_ir.active_skill}]\n")
print(reply)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Multi-turn conversation with skill switching
# MAGIC
# MAGIC The same agent instance can switch between skills across turns.

# COMMAND ----------

# Persistent agent across all turns
agent = CoworkerAgent(conversation_id="notebook-demo-multiturn")

# COMMAND ----------

# Turn 1 → routes to onboarding_coach
print(agent.handle_message(
    "I'm a new data engineer. Give me a quick overview of the parks business and the data warehouse."
))
print(f"\n→ Skill: {agent.active_skill}\n")

# COMMAND ----------

# Turn 2 → routes to schema_explorer
print(agent.handle_message(
    "Which tables should I focus on first, and what are the known column issues?"
))
print(f"\n→ Skill: {agent.active_skill}\n")

# COMMAND ----------

# Turn 3 → routes to data_detective
print(agent.handle_message(
    "Check the health of all three monitored tables right now and flag any anomalies."
))
print(f"\n→ Skill: {agent.active_skill}\n")

# COMMAND ----------

# Turn 4 → routes to pipeline_guardian
print(agent.handle_message(
    "Also check whether any ADF pipelines or Databricks jobs failed in the last 24 hours."
))
print(f"\n→ Skill: {agent.active_skill}\n")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Custom SQL Investigation

# COMMAND ----------

print(agent.handle_message(
    "Run a SQL query to check if there are any Voucher IDs in the SALES table "
    "that don't exist in the ATTENDANCE table. Show me the count and a few examples."
))
print(f"\n→ Skill: {agent.active_skill}\n")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Quick one-liner — ask anything (no conversation state)

# COMMAND ----------

# Simplest usage: one question, one answer
ask("What data quality issues should I know about in the ATTENDANCE table?")
