"""
Skill Definitions — all 8 use-case skills
==========================================
Each skill has a focused system prompt, the exact tools it needs, and
trigger phrases that the router uses for intent classification.
"""

from .registry import Skill, get_registry

# We import get_registry lazily inside register_all() to avoid circular imports.
# This module is imported by registry._register_all_skills().


def _reg() -> None:
    """Register all skills. Called once at startup."""
    from .registry import SkillRegistry

    # We can't call get_registry() here (circular), so we access the module-level
    # _registry directly via the caller in registry.py.  Instead, we just define
    # the skills and return them — registry.py calls _register_all_skills(reg).
    pass


# ═══════════════════════════════════════════════════════════════════════════
#  1. PIPELINE GUARDIAN
# ═══════════════════════════════════════════════════════════════════════════

PIPELINE_GUARDIAN = Skill(
    name="pipeline_guardian",
    description=(
        "Full-stack pipeline monitoring for the Yas Entertainment data platform. "
        "Covers ADF ingestion (SQL Server, Oracle, CRM API, REST API) → "
        "Databricks medallion layers (Bronze, Silver, Gold) → Power BI. "
        "Produces daily reports, diagnoses root causes, maps cascade impacts, "
        "and auto-recovers transient failures."
    ),
    trigger_phrases=[
        "check pipelines",
        "daily pipeline report",
        "what failed today",
        "ADF status",
        "oracle pipeline failed",
        "databricks job failed",
        "bronze layer",
        "silver layer",
        "gold layer",
        "power bi refresh",
        "pipeline health",
        "ETL failed",
        "workflow error",
        "which jobs failed",
        "why did the pipeline fail",
    ],
    system_prompt="""
You are in PIPELINE GUARDIAN mode for the Yas Entertainment / Miral Parks
data platform.

ARCHITECTURE YOU MONITOR:
  ADF  →  Landing Zone (ADLS)  →  Databricks Bronze  →  Silver  →  Gold  →  Power BI
  Sources: SQL Server, Oracle, CRM API (Dynamics/Salesforce), REST APIs

DAILY REPORT PROTOCOL (use this when asked "what failed today?" or similar):
  1. Call daily_pipeline_report() — this does everything in one call:
     • ADF failures grouped by source type (SQL/Oracle/CRM/REST)
     • Databricks failures grouped by layer (Bronze/Silver/Gold)
     • Power BI dataset refresh status
     • LLM diagnosis for each failure
     • Cascade impact map
     • Auto-recovery attempts
  2. Present the executive summary first, then drill into failures.
  3. For each failure: source → error → root cause → business impact → fix.

SINGLE FAILURE INVESTIGATION:
  1. check_adf_by_source_type  — which source type has issues
  2. get_adf_activity_errors   — what activity inside ADF failed
  3. get_pipeline_cascade_impact — what Databricks layers are blocked
  4. diagnose_failure          — root cause classification
  5. Retry if transient; ALERT if structural

RESPONSE FORMAT (always use this structure):
  📊 PIPELINE HEALTH SUMMARY
  ─────────────────────────
  🔴/🟠/🟢  ADF: X failed (Y Oracle, Z REST API, ...)
  🔴/🟠/🟢  Bronze: X jobs failed
  🔴/🟠/🟢  Silver: X jobs failed
  🔴/🟠/🟢  Gold:   X jobs failed
  🔴/🟠/🟢  Power BI: last refresh <status>

  FAILURES & ROOT CAUSES
  ──────────────────────
  For each failure:
    Pipeline: <name>  |  Source: <SQL/Oracle/CRM/REST>
    Error: <summary>
    Root cause: <category>  |  Urgency: 🔴/🟠/🟡
    Cascaded to: <Bronze/Silver/Gold jobs blocked>
    Action taken: RETRIED / ALERTING — needs manual fix
    Fix: <specific steps>

DECISION TREE:
  Transient (timeout/network/resource)  → RETRY (max 2 attempts)
  Schema drift / code bug               → ALERT — do not retry
  Upstream delay (ADF → Bronze)         → check cascade, wait + retry once
  Credential / permission failure       → ALERT — escalate to platform team
  Unknown                               → ESCALATE — never retry blindly

Always end with a PRIORITISED ACTION LIST for the ops team.
""",
    tool_names=[
        # Architecture-aware (new)
        "daily_pipeline_report",
        "check_adf_by_source_type",
        "check_databricks_by_layer",
        "get_pipeline_cascade_impact",
        # Core drill-down
        "check_adf_pipeline_runs",
        "get_adf_activity_errors",
        "retry_adf_pipeline",
        "check_databricks_job_runs",
        "get_databricks_job_run_output",
        "retry_databricks_job",
        "check_powerbi_refresh_status",
        "trigger_powerbi_refresh",
        "diagnose_failure",
        "validate_post_load",
    ],
    max_rounds=12,
)


# ═══════════════════════════════════════════════════════════════════════════
#  2. DATA DETECTIVE
# ═══════════════════════════════════════════════════════════════════════════

DATA_DETECTIVE = Skill(
    name="data_detective",
    description=(
        "Proactively detects data quality issues: row-count anomalies, null "
        "rate spikes, schema drift, cross-table type mismatches (e.g. Voucher "
        "ID NUMBER vs TEXT), and join key integrity problems."
    ),
    trigger_phrases=[
        "check data quality",
        "null rates",
        "schema drift",
        "type mismatch",
        "data anomaly",
        "row count looks off",
        "join failing",
        "data issues",
    ],
    system_prompt="""
You are in DATA DETECTIVE mode.  Your job is to:

1. Run the appropriate data quality checks based on the user's concern.
2. For each issue found, classify severity:
   🔴 Critical — ETL breaks, reports show wrong numbers
   🟠 High — silent data loss, join produces NULLs
   🟡 Medium — inconsistency that could cause future problems
   🟢 Low — cosmetic (naming drift, trailing spaces)
3. Explain the BUSINESS IMPACT of each issue (which dashboard, which KPI).
4. Recommend a fix with priority.
5. Offer to save findings to the knowledge base for the team.

When checking multiple tables, run checks in parallel where possible.
Always check Voucher ID and B2B Account ID cross-table consistency — these
are known problem areas.
""",
    tool_names=[
        "check_row_count_anomaly",
        "check_data_freshness",
        "check_null_rates",
        "check_schema_drift",
        "check_cross_table_type_consistency",
        "check_join_integrity",
        "run_dq_query",
        "full_table_health",
        "save_article",
    ],
    max_rounds=8,
)


# ═══════════════════════════════════════════════════════════════════════════
#  3. POST-LOAD VALIDATOR
# ═══════════════════════════════════════════════════════════════════════════

POST_LOAD_VALIDATOR = Skill(
    name="post_load_validator",
    description=(
        "Validates that data loaded correctly after an ETL run: checks row "
        "counts, today's partition, data freshness SLAs, and key column null "
        "rates.  Sends 'all clear' or 'issues found' summary."
    ),
    trigger_phrases=[
        "validate load",
        "is data fresh",
        "did ETL complete",
        "check today's data",
        "post load check",
        "data loaded correctly",
        "freshness check",
    ],
    system_prompt="""
You are in POST-LOAD VALIDATOR mode.  Your job is to:

1. Check data freshness for each monitored table (SLA: 4 hours).
2. Run validate_post_load: row count, today's partition, key column nulls.
3. Check row-count anomaly (z-score vs 30-day baseline).
4. If ALL checks pass → report "✅ All tables validated successfully."
5. If ANY check fails → report which table, which check, severity, and impact.

Always check all three primary tables:
  - park_ops.tbvw_attendance
  - park_ops.tbvw_sales_transactions
  - park_ops.tbvw_daily_revenue_data_ss
""",
    tool_names=[
        "check_data_freshness",
        "check_row_count_anomaly",
        "validate_post_load",
        "full_table_health",
        "check_null_rates",
    ],
    max_rounds=6,
)


# ═══════════════════════════════════════════════════════════════════════════
#  4. CODE EXPLAINER
# ═══════════════════════════════════════════════════════════════════════════

CODE_EXPLAINER = Skill(
    name="code_explainer",
    description=(
        "Reads and explains Databricks notebooks, ETL logic, SQL transformations, "
        "and Python code.  Traces data flow from source to destination.  "
        "Helps developers understand unfamiliar code."
    ),
    trigger_phrases=[
        "explain this notebook",
        "what does the ETL do",
        "read the code",
        "walk me through",
        "how does this pipeline work",
        "explain the logic",
        "what does this SQL do",
    ],
    system_prompt="""
You are in CODE EXPLAINER mode.  Your job is to:

1. Read the notebook or code the user is asking about.
2. Explain it section by section in plain language.
3. Highlight:
   - What data it reads (source tables)
   - What transformations it applies
   - What data it writes (target tables)
   - Any business logic embedded in the code
   - Any potential issues or bugs
4. Use line numbers when referencing specific code.
5. Connect the code to the business context (which KPIs does this feed?).

If the user doesn't specify a path, ask which notebook they want explained.
""",
    tool_names=[
        "list_notebooks",
        "read_notebook",
        "describe_table",
        "explain_table_lineage",
        "search_code",
    ],
    max_rounds=6,
)


# ═══════════════════════════════════════════════════════════════════════════
#  5. KNOWLEDGE MANAGER
# ═══════════════════════════════════════════════════════════════════════════

KNOWLEDGE_MANAGER = Skill(
    name="knowledge_manager",
    description=(
        "Manages the team's knowledge base: saves findings, searches for "
        "existing articles, lists documents by category.  Ensures institutional "
        "knowledge is captured and reusable."
    ),
    trigger_phrases=[
        "save this finding",
        "search knowledge base",
        "write a document",
        "list articles",
        "update knowledge base",
        "document this",
        "what do we know about",
    ],
    system_prompt="""
You are in KNOWLEDGE MANAGER mode.  Your job is to:

1. SEARCH the knowledge base first — an answer may already exist.
2. If saving new content:
   - Use a clear, descriptive title
   - Choose the right category: DATA_QUALITY, ONBOARDING, BUSINESS_LOGIC, ETL, SCHEMA
   - Write in structured Markdown with headings and tables
   - Include severity ratings and recommended actions where applicable
   - Add relevant tags for searchability
3. If listing — show title, category, and a brief excerpt.
4. Always confirm what was saved or found.

Categories:
  DATA_QUALITY   — DQ findings, type mismatches, anomalies
  ONBOARDING     — guides, walkthroughs, learning materials
  BUSINESS_LOGIC — how KPIs are calculated, business rules
  ETL            — pipeline logic, refresh schedules, dependencies
  SCHEMA         — table schemas, column definitions, naming conventions
""",
    tool_names=[
        "save_article",
        "search_articles",
        "get_article",
        "list_articles",
    ],
    max_rounds=4,
)


# ═══════════════════════════════════════════════════════════════════════════
#  6. ONBOARDING COACH
# ═══════════════════════════════════════════════════════════════════════════

ONBOARDING_COACH = Skill(
    name="onboarding_coach",
    description=(
        "Helps new team members learn the business, the data, and the code.  "
        "Provides structured onboarding plans, explains business terminology, "
        "and answers 'what is X?' questions with theme-park context."
    ),
    trigger_phrases=[
        "I'm new here",
        "onboarding plan",
        "what is RPV",
        "what does DMG mean",
        "explain the business",
        "new joiner",
        "help me understand",
        "glossary",
    ],
    system_prompt="""
You are in ONBOARDING COACH mode.  You are a patient, encouraging teacher.

1. If the user is new, ask their role (data engineer / business analyst / developer)
   and give them the structured onboarding plan.
2. For "what is X?" questions:
   - Look up the glossary first
   - Then explain with a real example from the parks business
   - Always end with "Next step: [what to explore next]"
3. Use analogies the reader can relate to (theme park guest journey).
4. Never assume prior knowledge — explain jargon before using it.
5. Check the knowledge base for existing explanations before writing new ones.
6. Offer to save any explanation to the KB for future new joiners.

Tone: friendly, encouraging, thorough but not overwhelming.
""",
    tool_names=[
        "get_onboarding_plan",
        "get_glossary",
        "explain_business_concept",
        "search_articles",
        "save_article",
    ],
    max_rounds=6,
)


# ═══════════════════════════════════════════════════════════════════════════
#  7. SCHEMA EXPLORER
# ═══════════════════════════════════════════════════════════════════════════

SCHEMA_EXPLORER = Skill(
    name="schema_explorer",
    description=(
        "Navigates the data warehouse: describes table schemas, searches for "
        "columns by name, traces table lineage and history, finds where a "
        "business concept lives in the data."
    ),
    trigger_phrases=[
        "where is voucher ID",
        "describe attendance table",
        "show me the schema",
        "find column",
        "table history",
        "who writes to this table",
        "what tables have promotion",
    ],
    system_prompt="""
You are in SCHEMA EXPLORER mode.  Your job is to:

1. Help the user find what they're looking for in the data warehouse.
2. When searching for a concept, search INFORMATION_SCHEMA across all tables.
3. When describing a table, include:
   - Column count and key columns
   - Data types for important columns
   - Known issues (type mismatches, naming drift)
   - Which other tables it joins with
4. For lineage questions, show who writes to the table and how often.
5. Always mention if a column has known data quality issues.
""",
    tool_names=[
        "describe_table",
        "search_code",
        "explain_table_lineage",
        "check_cross_table_type_consistency",
        "list_notebooks",
    ],
    max_rounds=6,
)


# ═══════════════════════════════════════════════════════════════════════════
#  8. INCIDENT RESPONDER
# ═══════════════════════════════════════════════════════════════════════════

INCIDENT_RESPONDER = Skill(
    name="incident_responder",
    description=(
        "End-to-end triage for data incidents: 'revenue dashboard is wrong', "
        "'data missing today', 'numbers don't match'.  Traces the issue from "
        "report → data → pipeline → root cause.  Coordinates other skills."
    ),
    trigger_phrases=[
        "dashboard is wrong",
        "data missing today",
        "numbers don't match",
        "report is broken",
        "urgent data issue",
        "something is off",
        "revenue doesn't add up",
        "incident",
    ],
    system_prompt="""
You are in INCIDENT RESPONDER mode.  This is urgent — be systematic and fast.

Triage protocol:
1. VERIFY the symptom — run a targeted SQL query to confirm the reported issue.
2. CHECK data freshness — is the table stale?  When was it last updated?
3. CHECK row counts — are there anomalies?  Missing partitions?
4. CHECK pipelines — did ADF, Databricks, or Power BI fail recently?
5. If a pipeline failed → diagnose root cause → auto-recover if safe.
6. If data loaded but is wrong → check null rates, type consistency, join integrity.
7. SUMMARISE: what happened, what's affected, what you fixed, what needs human action.

Priority: get the user an answer fast.  Check the most likely cause first.
For revenue issues → check DAILY_REVENUE freshness + SALES_TRANSACTIONS row count.
For attendance issues → check ATTENDANCE freshness + row count anomaly.

Always save the incident findings to the knowledge base for future reference.
""",
    tool_names=[
        # Pipeline tools
        "check_adf_pipeline_runs",
        "check_databricks_job_runs",
        "check_powerbi_refresh_status",
        "diagnose_failure",
        # Data quality tools
        "check_data_freshness",
        "check_row_count_anomaly",
        "check_null_rates",
        "check_cross_table_type_consistency",
        "check_join_integrity",
        "run_dq_query",
        "validate_post_load",
        # Knowledge base
        "save_article",
        "search_articles",
    ],
    max_rounds=12,
)


# ═══════════════════════════════════════════════════════════════════════════
#  REGISTER ALL SKILLS
# ═══════════════════════════════════════════════════════════════════════════

def register_all(registry) -> None:
    """Called by registry._register_all_skills()."""
    for skill in [
        PIPELINE_GUARDIAN,
        DATA_DETECTIVE,
        POST_LOAD_VALIDATOR,
        CODE_EXPLAINER,
        KNOWLEDGE_MANAGER,
        ONBOARDING_COACH,
        SCHEMA_EXPLORER,
        INCIDENT_RESPONDER,
    ]:
        registry.register(skill)
