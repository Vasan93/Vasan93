"""
Onboarding Tools
================
Structured onboarding paths for new joiners.  The agent uses these tools to
generate step-by-step learning plans, explain business concepts with examples
drawn from the actual data warehouse, and quiz understanding.
"""

from __future__ import annotations
import json


# ── Structured onboarding knowledge (embedded, not DB-dependent) ──────────

ONBOARDING_TRACKS = {
    "data_engineer": {
        "title": "Data Engineer Onboarding — Yas Entertainment / Miral Parks",
        "duration": "2 weeks",
        "steps": [
            {
                "day": "1-2",
                "topic": "Business Context",
                "goals": [
                    "Understand the 6 parks and their revenue models",
                    "Learn the guest journey: ticket purchase → gate entry → in-park spend → feedback",
                    "Know the 3 primary data views: ATTENDANCE, SALES_TRANSACTIONS, DAILY_REVENUE",
                ],
                "resources": ["Ask me: 'Explain the guest journey end to end'"],
            },
            {
                "day": "3-4",
                "topic": "Data Warehouse Architecture",
                "goals": [
                    "Understand Snowflake ↔ Databricks data flow",
                    "Map the key dimensions: Company → Department → Product hierarchy",
                    "Identify shared join keys (Account AK, Voucher ID, Promotion Key)",
                ],
                "resources": ["Ask me: 'Describe the Company-Department-Product hierarchy'"],
            },
            {
                "day": "5-6",
                "topic": "Known Data Quality Issues",
                "goals": [
                    "Understand the type mismatch on Voucher ID (NUMBER vs TEXT)",
                    "Know about naming drift: Id vs ID, y/n vs y n, trailing spaces",
                    "Learn which columns are missing from which tables and why it matters",
                ],
                "resources": ["Ask me: 'Run a full data quality audit'"],
            },
            {
                "day": "7-8",
                "topic": "ETL Pipelines",
                "goals": [
                    "Trace the ETL from source → staging → curated layer",
                    "Understand the refresh SLAs (ATTENDANCE: 4h, SALES: 4h, REVENUE: daily)",
                    "Read the main ETL notebooks and understand the transformation logic",
                ],
                "resources": ["Ask me: 'Show me the ETL lineage for tbvw_attendance'"],
            },
            {
                "day": "9-10",
                "topic": "Reporting & KPIs",
                "goals": [
                    "Understand how ATTENDANCE feeds the pax/day dashboard",
                    "Know how Revenue per Visitor (RPV) is calculated",
                    "Understand the Budget vs Actual vs Forecast columns in DAILY_REVENUE",
                ],
                "resources": ["Ask me: 'How is Revenue per Visitor calculated?'"],
            },
        ],
    },
    "business_analyst": {
        "title": "Business Analyst Onboarding — Yas Entertainment / Miral Parks",
        "duration": "1 week",
        "steps": [
            {
                "day": "1",
                "topic": "Company & Parks Overview",
                "goals": [
                    "Know all 6 parks, their target audiences, and seasonal patterns",
                    "Understand OMNI multi-park pass and Annual Pass programs",
                    "Learn the B2B agent and corporate booking channels",
                ],
                "resources": ["Ask me: 'Give me an overview of the parks business'"],
            },
            {
                "day": "2",
                "topic": "Key Metrics & Dashboards",
                "goals": [
                    "Know the KPIs: Pax/day, RPV, Yield, F&B per head, AP penetration",
                    "Understand which table feeds which dashboard",
                    "Learn how Budget, Forecast, and Actuals relate",
                ],
                "resources": ["Ask me: 'Explain all the KPIs and how they are calculated'"],
            },
            {
                "day": "3",
                "topic": "Promotions & Pricing",
                "goals": [
                    "Understand Promotion Key, OMNI Promotion, IG Discount codes",
                    "Know how Offer Amount and Offer Percentage flow through the data",
                    "Learn the Promotion Classification and DMG hierarchy",
                ],
                "resources": ["Ask me: 'How does the promotion data flow work?'"],
            },
            {
                "day": "4-5",
                "topic": "Data Caveats",
                "goals": [
                    "Understand why the same column can show different numbers in ATT vs SAL",
                    "Know about data quality issues that affect reports",
                    "Learn how to spot and report a data discrepancy",
                ],
                "resources": ["Ask me: 'What data caveats should a BA know about?'"],
            },
        ],
    },
    "new_developer": {
        "title": "Developer Onboarding — Yas Entertainment / Miral Parks",
        "duration": "2 weeks",
        "steps": [
            {
                "day": "1-2",
                "topic": "Codebase & Repo Structure",
                "goals": [
                    "Clone the repos and set up your Databricks workspace",
                    "Understand the notebook folder structure (bronze/silver/gold)",
                    "Identify the main ETL entry points and scheduling configuration",
                ],
                "resources": ["Ask me: 'Walk me through the repo structure'"],
            },
            {
                "day": "3-5",
                "topic": "Core ETL Logic",
                "goals": [
                    "Read the ATTENDANCE ETL notebook end to end",
                    "Understand how Snowflake views map to Delta tables",
                    "Trace a single record from source to the final view",
                ],
                "resources": ["Ask me: 'Explain the ATTENDANCE ETL step by step'"],
            },
            {
                "day": "6-8",
                "topic": "Schema & Data Model",
                "goals": [
                    "Understand the 230+ column ATTENDANCE schema",
                    "Know the naming conventions (and known violations)",
                    "Learn the shared key columns and how tables join",
                ],
                "resources": ["Ask me: 'Describe the ATTENDANCE schema in detail'"],
            },
            {
                "day": "9-10",
                "topic": "Testing & Data Quality",
                "goals": [
                    "Understand the existing schema_comparison.py script",
                    "Learn to write data quality checks using the Co-Worker agent tools",
                    "Practice: run a null-rate audit and fix a found issue",
                ],
                "resources": ["Ask me: 'Help me write a data quality check'"],
            },
        ],
    },
}


BUSINESS_GLOSSARY = {
    "Pax": "Short for 'passengers' — counts the number of guests entering a park.",
    "RPV": "Revenue Per Visitor = Total Revenue ÷ Total Attendance.  Key profitability metric.",
    "OMNI Pass": "Multi-park annual pass that works across all Yas Island parks.",
    "DMG": "Department Management Group — the org hierarchy used for P&L ownership.",
    "Annual Pass (AP)": "A season ticket valid for a year.  'AP Penetration' = AP holders ÷ total visitors.",
    "Yield per Ticket": "Net ticket revenue ÷ tickets sold.  Measures pricing effectiveness.",
    "F&B per Head": "Food & Beverage spend ÷ visitors on that day.  Measures in-park spending.",
    "EH Booking": "Entertainment Hotspot — an external booking channel for events and packages.",
    "IG Discount": "In-Gate discount — promotions applied at the point of entry.",
    "B2B Agent": "Business-to-business travel agent who bulk-books tickets for groups.",
    "Account AK": "Alternate Key for customer CRM accounts.  Used to link guest profiles across tables.",
    "Workstation AK": "Alternate Key identifying the physical POS terminal where the transaction happened.",
    "Voucher ID": "Identifier for discount vouchers.  Known type mismatch: NUMBER in ATT/REV, TEXT in SAL.",
    "Promotion Key": "Surrogate key linking to the promotions dimension.  Shared across all 3 tables.",
    "TBVW": "Table View — prefix convention for Snowflake views surfaced to reporting.",
    "Bronze / Silver / Gold": "Medallion architecture: Bronze = raw ingestion, Silver = cleaned, Gold = business-ready.",
    "Unity Catalog": "Databricks governance layer — manages access, lineage, and audit for all data assets.",
    "SLA": "Service Level Agreement — e.g. 'ATTENDANCE table must refresh every 4 hours during operations'.",
}


# ── Tool functions ────────────────────────────────────────────────────────

def get_onboarding_plan(role: str) -> str:
    """Return the structured onboarding plan for a given role."""
    key = role.lower().replace(" ", "_")
    plan = ONBOARDING_TRACKS.get(key)
    if plan is None:
        return json.dumps({
            "error": f"No onboarding track for role '{role}'.",
            "available_roles": list(ONBOARDING_TRACKS.keys()),
        })
    return json.dumps(plan, indent=2)


def get_glossary(term: str | None = None) -> str:
    """Return the business glossary, optionally filtered to a specific term."""
    if term:
        matches = {
            k: v for k, v in BUSINESS_GLOSSARY.items()
            if term.lower() in k.lower() or term.lower() in v.lower()
        }
        if not matches:
            return json.dumps({
                "query": term,
                "results": [],
                "hint": "Try a shorter keyword, or ask me to explain the concept directly.",
            })
        return json.dumps({"query": term, "results": matches})
    return json.dumps({"glossary": BUSINESS_GLOSSARY})


def explain_business_concept(concept: str) -> str:
    """
    Return structured context for the agent to build an explanation.
    The agent will enrich this with its system-prompt knowledge.
    """
    concept_lower = concept.lower()

    # Map concepts to the relevant tables and columns
    concept_map = {
        "attendance": {
            "tables": ["park_ops.tbvw_attendance"],
            "key_columns": ["Attendance Date", "Sale Company Name", "Product Name", "Ticket Type", "Annual Pass Flag"],
            "related_kpis": ["Pax/day", "AP Penetration"],
            "tip": "Attendance = one row per admission event, not per transaction.",
        },
        "revenue": {
            "tables": ["park_ops.tbvw_daily_revenue_data_ss", "park_ops.tbvw_sales_transactions"],
            "key_columns": ["Revenue Category", "Net Revenue", "Gross Revenue", "Budget Revenue", "Forecast Revenue"],
            "related_kpis": ["RPV", "Yield per Ticket", "F&B per Head"],
            "tip": "DAILY_REVENUE is day-level aggregation; SALES_TRANSACTIONS is line-item detail.",
        },
        "promotion": {
            "tables": ["park_ops.tbvw_attendance", "park_ops.tbvw_sales_transactions"],
            "key_columns": ["Promotion Key", "OMNI Promotion Name", "OMNI Promotion Code", "Promotion Type", "Promotion Classification", "IG Discount Code", "Offer Amount", "Offer Percentage"],
            "related_kpis": ["Promo ROI", "Discount Rate"],
            "tip": "Promotions span two systems: OMNI (multi-park) and IG (in-gate). Check both.",
        },
        "annual pass": {
            "tables": ["park_ops.tbvw_attendance"],
            "key_columns": ["Annual Pass Flag", "Yas Park Pass", "OMNI Annual Pass y/n", "OMNI Multipark y/n", "OMNI Park Combination"],
            "related_kpis": ["AP Penetration", "AP Revenue"],
            "tip": "Flags differ: ATT uses 'y/n', SAL uses 'y n'. Watch for join issues.",
        },
        "voucher": {
            "tables": ["All three"],
            "key_columns": ["Voucher ID", "Voucher Account ID", "Voucher Type", "Voucher Company Name"],
            "related_kpis": ["Voucher Utilisation Rate"],
            "tip": "CRITICAL: Voucher ID is NUMBER in ATT/REV but TEXT in SAL. Direct JOIN will fail.",
        },
    }

    # Find the best match
    matched = None
    for key, val in concept_map.items():
        if key in concept_lower:
            matched = val
            break

    if matched:
        return json.dumps({"concept": concept, **matched})

    return json.dumps({
        "concept": concept,
        "hint": (
            "No pre-mapped context for this concept.  I'll use my business "
            "domain knowledge to explain it.  Try asking about: attendance, "
            "revenue, promotion, annual pass, or voucher."
        ),
    })


# ── OpenAI tool schemas ──────────────────────────────────────────────────

ONBOARDING_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_onboarding_plan",
            "description": (
                "Get a structured day-by-day onboarding plan for a new joiner.  "
                "Available roles: data_engineer, business_analyst, new_developer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "enum": ["data_engineer", "business_analyst", "new_developer"],
                    },
                },
                "required": ["role"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_glossary",
            "description": "Look up a business or technical term in the Yas Entertainment glossary.  Omit 'term' to get the full glossary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "term": {"type": "string", "description": "Term to look up (case-insensitive partial match)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_business_concept",
            "description": (
                "Get structured context about a business concept — which tables, "
                "columns, and KPIs are related.  Use this to build rich explanations "
                "for new joiners or business stakeholders."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "concept": {"type": "string", "description": "e.g. 'attendance', 'revenue', 'promotion', 'annual pass', 'voucher'"},
                },
                "required": ["concept"],
            },
        },
    },
]


def run_onboarding_tool(name: str, args: dict) -> str:
    handlers = {
        "get_onboarding_plan":     get_onboarding_plan,
        "get_glossary":            get_glossary,
        "explain_business_concept": explain_business_concept,
    }
    fn = handlers.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown onboarding tool: {name}"})
    try:
        return fn(**args)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
