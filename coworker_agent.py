"""
Co-Worker Agent for Yas Entertainment / Miral Parks
====================================================
An intelligent co-worker that combines:
  1. Business domain expertise  (entertainment / parks / data warehouse)
  2. Technical code understanding (Python, Snowflake, ETL)
  3. Data issue detection        (schema, quality, consistency)
  4. Knowledge sharing           (documents findings as reusable knowledge)

Usage:
    python coworker_agent.py                      # interactive mode
    python coworker_agent.py "your question here" # single-shot mode
    python coworker_agent.py --audit              # run full data-quality audit
    python coworker_agent.py --kb                 # show knowledge-base index
"""

import sys
import os
import anyio
import argparse
from pathlib import Path
from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AgentDefinition,
    ResultMessage,
    SystemMessage,
    AssistantMessage,
    TextBlock,
    list_sessions,
    get_session_messages,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent
KB_DIR = REPO_ROOT / "knowledge_base"
KB_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# System prompt — business + technical context for the orchestrator
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = f"""
You are the Co-Worker Agent for **Yas Entertainment / Miral Parks**, a leading
theme-park and entertainment operator in Abu Dhabi (UAE).  You serve as an
always-available expert colleague who combines deep business knowledge with
strong technical and data skills.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BUSINESS DOMAIN KNOWLEDGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Parks operated: Ferrari World, Yas Waterworld, Warner Bros. World, Clymb,
  Sea World Yas Island, ILYAS & MUSTAFA GALADARI Museum of the Future.
• Revenue streams: ticket sales, annual passes, F&B, retail, group bookings,
  hotel/park packages, OMNI multi-park passes.
• Guest segments: residents, tourists, families, corporate, Etihad loyalty members.
• Seasonal patterns: peak during school holidays, UAE National Day, Ramadan dips.
• Key KPIs: Attendance (pax/day), Revenue per visitor (RPV), Yield per ticket,
  F&B spend per head, Annual-pass penetration, Channel mix (direct/OTA/corporate).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATA WAREHOUSE SCHEMA (Snowflake)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Three primary views drive operational reporting:

  TBVW_ATTENDANCE          — Guest admission records, park entry,
                             product/ticket details, customer demographics,
                             promotion info, season-pass flags.

  TBVW_SALES_TRANSACTIONS  — Point-of-sale transactions across all revenue
                             channels (tickets, F&B, retail, hotel packages),
                             payment methods, voucher/discount usage.

  TBVW__DAILY_REVENUE_DATA_SS — Day-level aggregated financial data, revenue
                             category breakdown, park-level P&L indicators.

Key shared columns: Date keys, Company/Department/Product hierarchies,
Promotion keys, Account AK, Workstation AK, Voucher IDs, Currency fields.

Known data-quality patterns to watch:
  • TYPE MISMATCHES  — same column name stored as TEXT in one table, NUMBER
                       in another (e.g., Voucher ID).
  • NAMING DRIFT    — inconsistent capitalisation (Id vs ID), trailing/leading
                      spaces, typos (Attendence, Datet).
  • FLAG CONVENTIONS — y/n vs Y N vs boolean; length 13 vs 14 for flag fields.
  • MISSING COLUMNS  — columns shared by 2 tables but absent from the 3rd,
                       causing silent NULL joins in ETL.
  • LENGTH SKEW      — same TEXT column capped differently across tables
                       (e.g., 200 vs 16 777 216), breaking UNION queries.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR CAPABILITIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. CODE ANALYSIS   — Read, understand, and explain the Python scripts in this
                     repo.  Identify what each section does and why.
2. DATA DETECTIVE  — Detect schema anomalies, type mismatches, naming issues,
                     and missing columns.  Explain the business impact of each.
3. KNOWLEDGE SHARE — Write clear, structured summaries into the knowledge base
                     at {KB_DIR}  so findings persist and are reusable.
4. BUSINESS BRIDGE — Translate technical issues into plain business language;
                     explain why a VARCHAR/NUMBER mismatch breaks the revenue
                     dashboard, for example.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BEHAVIOUR GUIDELINES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Delegate deep-dive tasks to your specialist sub-agents when appropriate.
• Always link technical findings to their business impact.
• When writing to the knowledge base use clear Markdown with headings, tables,
  and severity ratings (Critical / High / Medium / Low).
• Be concise in chat; be comprehensive in knowledge-base documents.
• If you don't know something, say so — don't hallucinate column names or
  business rules.
"""

# ---------------------------------------------------------------------------
# Sub-agent definitions
# ---------------------------------------------------------------------------
CODE_ANALYST_PROMPT = """
You are a Python and Snowflake code analyst.  Your job is to read source files,
understand what they do, identify bugs or inefficiencies, and explain the logic
clearly.  You have access to Read, Glob, and Grep tools.  Always quote specific
line numbers when you reference code.
"""

DATA_DETECTIVE_PROMPT = """
You are a data-quality specialist for Snowflake data warehouses.  Your job is to:
  - Identify type mismatches, naming inconsistencies, trailing spaces, and missing
    columns across schema definitions.
  - Classify each issue by severity: Critical (breaks ETL/joins), High (causes
    silent data loss), Medium (inconsistency risk), Low (cosmetic).
  - Produce a structured report with column name, tables affected, issue type,
    and recommended fix.
You have Read, Glob, and Grep tools to inspect schema files.
"""

KNOWLEDGE_CURATOR_PROMPT = """
You are a technical documentation specialist.  Given findings from code or data
analysis, you write clear, well-structured Markdown documents for the knowledge
base.  Documents must include:
  - Title and date
  - Executive summary (2-3 sentences, business language)
  - Detailed findings table
  - Recommended actions with priority
  - Impact assessment
You have Read and Write tools.  Write files to the knowledge_base/ directory.
"""

BUSINESS_ADVISOR_PROMPT = """
You are a business analyst for a theme-park operator.  Given a technical data or
code issue, you explain:
  - What it means in plain English for business users
  - Which KPIs or reports are affected
  - What decisions could be wrong because of this issue
  - Urgency: how quickly should this be fixed?
You have Read and Grep tools to look up relevant context.
"""

SUB_AGENTS: dict[str, AgentDefinition] = {
    "code-analyst": AgentDefinition(
        description="Reads and explains Python/Snowflake code in this repository.",
        prompt=CODE_ANALYST_PROMPT,
        tools=["Read", "Glob", "Grep"],
    ),
    "data-detective": AgentDefinition(
        description="Detects schema anomalies, type mismatches, and naming issues.",
        prompt=DATA_DETECTIVE_PROMPT,
        tools=["Read", "Glob", "Grep"],
    ),
    "knowledge-curator": AgentDefinition(
        description="Writes structured Markdown documents to the knowledge base.",
        prompt=KNOWLEDGE_CURATOR_PROMPT,
        tools=["Read", "Write"],
    ),
    "business-advisor": AgentDefinition(
        description="Translates technical issues into business impact analysis.",
        prompt=BUSINESS_ADVISOR_PROMPT,
        tools=["Read", "Grep"],
    ),
}

# ---------------------------------------------------------------------------
# Common agent options factory
# ---------------------------------------------------------------------------
def make_options(resume: str | None = None, extra_tools: list[str] | None = None) -> ClaudeAgentOptions:
    tools = ["Read", "Glob", "Grep", "Write", "Agent"]
    if extra_tools:
        tools.extend(extra_tools)
    opts = ClaudeAgentOptions(
        cwd=str(REPO_ROOT),
        allowed_tools=tools,
        permission_mode="acceptEdits",
        system_prompt=SYSTEM_PROMPT,
        model="claude-opus-4-6",
        agents=SUB_AGENTS,
        max_turns=30,
    )
    if resume:
        opts.resume = resume
    return opts


# ---------------------------------------------------------------------------
# Helper: print streamed assistant text
# ---------------------------------------------------------------------------
def _print_assistant(message: AssistantMessage) -> None:
    for block in message.content:
        if isinstance(block, TextBlock) and block.text.strip():
            print(block.text, end="", flush=True)


# ---------------------------------------------------------------------------
# Single query execution
# ---------------------------------------------------------------------------
async def run_query(prompt: str, resume: str | None = None) -> str:
    """Run a single prompt and return the result text."""
    result_text = ""
    session_id = resume

    async for message in query(prompt=prompt, options=make_options(resume=resume)):
        if isinstance(message, SystemMessage) and message.subtype == "init":
            session_id = message.data.get("session_id")
        elif isinstance(message, AssistantMessage):
            _print_assistant(message)
        elif isinstance(message, ResultMessage):
            result_text = message.result

    if not result_text:
        print()  # trailing newline if we printed streamed chunks
    return result_text, session_id


# ---------------------------------------------------------------------------
# Audit mode — comprehensive data-quality report
# ---------------------------------------------------------------------------
AUDIT_PROMPT = """
Perform a full Co-Worker audit of this repository.  Work through these steps:

1. Use the **code-analyst** sub-agent to read schema_comparison.py and produce
   a structured summary of: what the script does, its four analysis sections,
   the three tables it covers, and any code-level issues.

2. Use the **data-detective** sub-agent to analyze all column definitions in
   schema_comparison.py and produce a severity-classified report of every
   data-quality issue found (type mismatches, naming inconsistencies, trailing
   spaces, missing columns, length mismatches).

3. Use the **business-advisor** sub-agent to take the data-detective's findings
   and explain the business impact in plain language — which reports break,
   which KPIs are at risk, and what urgency level each issue deserves.

4. Use the **knowledge-curator** sub-agent to write two Markdown files:
   - knowledge_base/DATA_QUALITY_ISSUES.md  — full technical findings table
   - knowledge_base/BUSINESS_IMPACT.md      — business-friendly impact summary

5. Finally, print a brief executive summary (5-8 bullets) covering the most
   critical findings and recommended next steps.
"""

async def run_audit() -> None:
    print("\n" + "=" * 70)
    print("  CO-WORKER AUDIT — Yas Entertainment / Miral Parks Data Warehouse")
    print("=" * 70 + "\n")
    _, _ = await run_query(AUDIT_PROMPT)
    print("\n\nAudit complete.  Knowledge base updated in:", KB_DIR)


# ---------------------------------------------------------------------------
# Knowledge base index
# ---------------------------------------------------------------------------
async def show_kb_index() -> None:
    docs = sorted(KB_DIR.glob("*.md"))
    if not docs:
        print("Knowledge base is empty.  Run --audit to populate it.")
        return
    print(f"\nKnowledge Base — {len(docs)} document(s) in {KB_DIR}\n")
    for doc in docs:
        lines = doc.read_text().splitlines()
        title = next((l.lstrip("# ").strip() for l in lines if l.startswith("#")), doc.name)
        # Extract first non-heading, non-empty line as description
        desc = next(
            (l.strip() for l in lines if l.strip() and not l.startswith("#")),
            ""
        )
        size = doc.stat().st_size
        print(f"  {doc.name:<40}  {size:>6} bytes  — {desc[:60]}")


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------
async def run_interactive() -> None:
    print("\n" + "=" * 70)
    print("  CO-WORKER AGENT  —  Yas Entertainment / Miral Parks")
    print("=" * 70)
    print("Type your question or command.  Special commands:")
    print("  /audit   — run full data-quality audit")
    print("  /kb      — list knowledge base documents")
    print("  /history — show recent sessions")
    print("  /quit    — exit\n")

    session_id: str | None = None

    while True:
        try:
            user_input = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
            print("Goodbye!")
            break

        if user_input.lower() == "/audit":
            await run_audit()
            session_id = None  # fresh session after audit
            continue

        if user_input.lower() == "/kb":
            await show_kb_index()
            continue

        if user_input.lower() == "/history":
            sessions = list_sessions()
            if not sessions:
                print("No previous sessions found.")
            else:
                print(f"\nLast {min(5, len(sessions))} sessions:")
                for s in sessions[:5]:
                    print(f"  {s.session_id[:16]}…  cwd={s.cwd}")
            continue

        print("\nAgent > ", end="", flush=True)
        _, new_session_id = await run_query(user_input, resume=session_id)
        if new_session_id:
            session_id = new_session_id  # maintain conversational context
        print("\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Co-Worker Agent for Yas Entertainment / Miral Parks"
    )
    parser.add_argument("prompt", nargs="?", help="Single-shot prompt")
    parser.add_argument("--audit", action="store_true", help="Run full data-quality audit")
    parser.add_argument("--kb", action="store_true", help="Show knowledge-base index")
    args = parser.parse_args()

    if args.audit:
        await run_audit()
    elif args.kb:
        await show_kb_index()
    elif args.prompt:
        print("\nAgent > ", end="", flush=True)
        result, _ = await run_query(args.prompt)
        print()
    else:
        await run_interactive()


if __name__ == "__main__":
    anyio.run(main)
