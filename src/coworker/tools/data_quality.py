"""
Data-Quality Tools
==================
These tools give the agent the ability to run live, intelligent checks against
the Databricks / Snowflake tables.  Each function returns a structured JSON
string that the LLM can reason over.

Uses db_client for database access — works on both Databricks clusters
(SparkSession) and Databricks Apps (SQL Connector to a serverless warehouse).
"""

from __future__ import annotations
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import cfg
from ..db_client import get_db


# ── helpers ────────────────────────────────────────────────────────────────

def _safe_table(name: str) -> str:
    """Validate table name to prevent SQL injection."""
    if not re.fullmatch(r"[\w.]+", name):
        raise ValueError(f"Invalid table name: '{name}'")
    return name


def _to_json(obj: Any) -> str:
    return json.dumps(obj, default=str, indent=2)


# ── Tool 1: Row-count anomaly detection ────────────────────────────────────

def check_row_count_anomaly(table: str, date_col: str = "auto") -> str:
    """
    Compare today's row count against a 30-day rolling mean + 2-sigma threshold.
    Returns severity, z-score, and a plain-language explanation.
    """
    db = get_db()
    tbl = _safe_table(table)

    # Auto-detect a date column if not specified
    if date_col == "auto":
        cols = [c["name"].lower() for c in db.get_columns(tbl)]
        candidates = [c for c in cols if "date" in c and "key" not in c]
        date_col = candidates[0] if candidates else None

    if not date_col:
        return _to_json({"error": "No date column found; pass date_col explicitly."})

    sql = f"""
        WITH daily AS (
            SELECT
                CAST({date_col} AS DATE) AS load_date,
                COUNT(*) AS row_count
            FROM {tbl}
            WHERE {date_col} >= DATEADD(day, -{cfg.BASELINE_DAYS + 1}, CURRENT_DATE())
            GROUP BY 1
        ),
        stats AS (
            SELECT
                AVG(row_count)    AS mean_count,
                STDDEV(row_count) AS std_count
            FROM daily
            WHERE load_date < CURRENT_DATE()
        )
        SELECT
            d.load_date,
            d.row_count,
            s.mean_count,
            s.std_count,
            ROUND((d.row_count - s.mean_count) / NULLIF(s.std_count, 0), 2) AS z_score
        FROM daily d
        CROSS JOIN stats s
        WHERE d.load_date = CURRENT_DATE()
    """
    rows = db.execute(sql)

    if not rows:
        return _to_json({
            "table": tbl,
            "status": "NO_DATA_TODAY",
            "severity": "CRITICAL",
            "message": (
                f"Table {tbl} has zero rows for today.  "
                "ETL may have failed or the load window has not started yet."
            ),
        })

    row = rows[0]
    z = float(row.get("z_score") or 0)
    count = int(row.get("row_count", 0))
    mean = float(row.get("mean_count") or 0)
    std  = float(row.get("std_count") or 1)

    if abs(z) > 3:
        severity, emoji = "CRITICAL", "🔴"
    elif abs(z) > 2:
        severity, emoji = "HIGH", "🟠"
    elif abs(z) > 1.5:
        severity, emoji = "MEDIUM", "🟡"
    else:
        severity, emoji = "OK", "🟢"

    direction = "ABOVE" if z > 0 else "BELOW"
    return _to_json({
        "table": tbl,
        "date": str(row.get("load_date")),
        "today_count": count,
        "baseline_mean": round(mean, 0),
        "baseline_std":  round(std, 0),
        "z_score": z,
        "severity": severity,
        "summary": (
            f"{emoji} [{severity}] {tbl}: {count:,} rows today — "
            f"{abs(z):.1f}σ {direction} the {cfg.BASELINE_DAYS}-day average "
            f"({mean:,.0f} ± {std:,.0f}).  "
            + (
                "This deviation is large enough to indicate an ETL incident."
                if severity in ("CRITICAL", "HIGH")
                else "Within normal range."
            )
        ),
    })


# ── Tool 2: Data freshness ─────────────────────────────────────────────────

def check_data_freshness(table: str, max_hours_stale: float = 4.0) -> str:
    """
    Check when the table was last modified and whether it exceeds the SLA.
    """
    db = get_db()
    tbl = _safe_table(table)

    # Use DESCRIBE HISTORY (Delta) for last write timestamp
    try:
        hist = db.execute(f"DESCRIBE HISTORY {tbl} LIMIT 1")
        if hist:
            last_op = hist[0]
            ts_str = str(last_op.get("timestamp", ""))
            last_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        else:
            return _to_json({"error": "DESCRIBE HISTORY returned nothing."})
    except Exception as exc:
        return _to_json({"error": str(exc)})

    now = datetime.now(timezone.utc)
    hours_old = (now - last_ts).total_seconds() / 3600

    if hours_old > max_hours_stale * 3:
        severity = "CRITICAL"
    elif hours_old > max_hours_stale:
        severity = "HIGH"
    else:
        severity = "OK"

    return _to_json({
        "table": tbl,
        "last_updated_utc": ts_str,
        "hours_since_update": round(hours_old, 2),
        "sla_hours": max_hours_stale,
        "severity": severity,
        "summary": (
            f"{'🔴' if severity == 'CRITICAL' else '🟠' if severity == 'HIGH' else '🟢'} "
            f"[{severity}] {tbl} last updated {hours_old:.1f}h ago "
            f"(SLA: ≤{max_hours_stale}h)."
        ),
    })


# ── Tool 3: Null-rate audit ────────────────────────────────────────────────

def check_null_rates(
    table: str,
    columns: list[str] | None = None,
    threshold_pct: float = 5.0,
) -> str:
    """
    Check null rates for specified columns (or all columns if none given).
    Returns columns that exceed the threshold.
    """
    db = get_db()
    tbl = _safe_table(table)

    if columns is None:
        columns = [c["name"] for c in db.get_columns(tbl)
                   if "key" in c["name"].lower() or "id" in c["name"].lower()]
        columns = columns[:20]  # cap to avoid mega-queries

    exprs = [
        f"ROUND(100.0 * SUM(CASE WHEN `{c}` IS NULL THEN 1 ELSE 0 END) "
        f"/ COUNT(*), 2) AS `{c}`"
        for c in columns
    ]
    row = db.execute(
        f"SELECT {', '.join(exprs)} FROM {tbl} "
        f"LIMIT {cfg.DQ_SAMPLE_ROWS}"
    )[0]

    issues = [
        {"column": col, "null_pct": pct, "severity": "HIGH" if pct > 20 else "MEDIUM"}
        for col, pct in row.items()
        if pct is not None and float(pct) > threshold_pct
    ]

    return _to_json({
        "table": tbl,
        "columns_checked": len(columns),
        "issues_found": len(issues),
        "threshold_pct": threshold_pct,
        "issues": issues,
        "summary": (
            f"{'🔴' if any(i['severity'] == 'HIGH' for i in issues) else '🟡' if issues else '🟢'} "
            f"{len(issues)} column(s) exceed {threshold_pct}% null rate in {tbl}."
        ),
    })


# ── Tool 4: Schema drift detection ────────────────────────────────────────

def check_schema_drift(table: str, expected_columns: list[str]) -> str:
    """
    Compare the live schema to an expected column list.
    Returns added / removed / type-changed columns.
    """
    db = get_db()
    tbl = _safe_table(table)

    live_cols = {c["name"]: c["type"] for c in db.get_columns(tbl)}
    live_set = set(live_cols.keys())
    expected_set = set(expected_columns)

    added   = sorted(live_set - expected_set)
    removed = sorted(expected_set - live_set)

    severity = "OK"
    if removed:
        severity = "CRITICAL"
    elif added:
        severity = "MEDIUM"

    return _to_json({
        "table": tbl,
        "columns_added":   added,
        "columns_removed": removed,
        "severity": severity,
        "summary": (
            f"{'🔴' if removed else '🟡' if added else '🟢'} "
            f"Schema drift: {len(removed)} column(s) removed, "
            f"{len(added)} column(s) added vs. expected schema."
        ),
    })


# ── Tool 5: Cross-table type consistency ──────────────────────────────────

def check_cross_table_type_consistency(
    column_name: str,
    tables: list[str] | None = None,
) -> str:
    """
    Check whether a shared column has the same data type across all three
    primary tables.  Returns a comparison matrix and severity.
    """
    db = get_db()
    if tables is None:
        tables = cfg.MONITORED_TABLES

    result: dict[str, str | None] = {}
    for tbl in tables:
        try:
            cols = db.get_columns(_safe_table(tbl))
            match = next(
                (c["type"] for c in cols if c["name"].lower() == column_name.lower()),
                None,
            )
            result[tbl] = match
        except Exception as exc:
            result[tbl] = f"ERROR: {exc}"

    types_found = set(v for v in result.values() if v and not v.startswith("ERROR"))
    severity = "CRITICAL" if len(types_found) > 1 else "OK"

    return _to_json({
        "column": column_name,
        "type_by_table": result,
        "unique_types": sorted(types_found),
        "severity": severity,
        "summary": (
            f"{'🔴' if severity == 'CRITICAL' else '🟢'} "
            f"'{column_name}': "
            + (
                f"TYPE MISMATCH — found {sorted(types_found)} across tables. "
                "Joins and UNION queries will fail or produce incorrect results."
                if severity == "CRITICAL"
                else f"Consistent type ({next(iter(types_found))}) across all tables."
            )
        ),
    })


# ── Tool 6: Join key integrity ─────────────────────────────────────────────

def check_join_integrity(
    left_table: str,
    right_table: str,
    key_column: str,
    sample_date: str | None = None,
) -> str:
    """
    Count orphaned keys: records in left_table whose key_column value does
    not exist in right_table.  Optionally filter to a specific date.
    """
    db = get_db()
    lt = _safe_table(left_table)
    rt = _safe_table(right_table)

    date_filter = f"WHERE CAST(`{key_column}` AS DATE) = '{sample_date}'" if sample_date else ""

    sql = f"""
        SELECT
            COUNT(*)                                    AS total_left,
            SUM(CASE WHEN r.`{key_column}` IS NULL THEN 1 ELSE 0 END) AS orphans,
            ROUND(
                100.0 * SUM(CASE WHEN r.`{key_column}` IS NULL THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0), 2
            ) AS orphan_pct
        FROM {lt} l
        LEFT JOIN {rt} r USING (`{key_column}`)
        {date_filter}
    """
    row = db.execute(sql)[0]
    orphan_pct = float(row.get("orphan_pct") or 0)

    if orphan_pct > 10:
        severity = "CRITICAL"
    elif orphan_pct > 2:
        severity = "HIGH"
    elif orphan_pct > 0:
        severity = "MEDIUM"
    else:
        severity = "OK"

    return _to_json({
        "left_table":   lt,
        "right_table":  rt,
        "key_column":   key_column,
        "total_left":   row.get("total_left"),
        "orphans":      row.get("orphans"),
        "orphan_pct":   orphan_pct,
        "severity":     severity,
        "summary": (
            f"{'🔴' if severity == 'CRITICAL' else '🟠' if severity == 'HIGH' else '🟡' if severity == 'MEDIUM' else '🟢'} "
            f"Join integrity {lt} ↔ {rt} on '{key_column}': "
            f"{row.get('orphans', 0):,} orphan records ({orphan_pct}%)."
        ),
    })


# ── Tool 7: Run arbitrary DQ SQL ──────────────────────────────────────────

def run_dq_query(sql: str, description: str = "") -> str:
    """
    Execute a read-only SQL query for ad-hoc data quality investigation.
    Results are capped at 200 rows to keep the context window manageable.
    Only SELECT statements are permitted.
    """
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        return _to_json({"error": "Only SELECT statements are allowed."})

    db = get_db()
    records = db.execute(sql, limit=200)

    return _to_json({
        "description": description,
        "row_count":   len(records),
        "results":     records,
    })


# ── Tool 8: Full table health report ──────────────────────────────────────

def full_table_health(table: str) -> str:
    """
    Run freshness + row-count anomaly checks together for a quick overview.
    """
    freshness = json.loads(check_data_freshness(table))
    anomaly   = json.loads(check_row_count_anomaly(table))

    overall_severity = max(
        ["OK", "LOW", "MEDIUM", "HIGH", "CRITICAL"].index(
            freshness.get("severity", "OK")
        ),
        ["OK", "LOW", "MEDIUM", "HIGH", "CRITICAL"].index(
            anomaly.get("severity", "OK")
        ),
    )
    severity_name = ["OK", "LOW", "MEDIUM", "HIGH", "CRITICAL"][overall_severity]

    return _to_json({
        "table":            table,
        "overall_severity": severity_name,
        "freshness":        freshness,
        "row_count_check":  anomaly,
    })


# ── OpenAI tool schemas ────────────────────────────────────────────────────

DATA_QUALITY_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "check_row_count_anomaly",
            "description": (
                "Detect whether today's row count for a table is statistically "
                "anomalous compared to the 30-day baseline (Z-score method). "
                "Use this proactively when the user asks about data volumes, "
                "ETL health, or if something looks off."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "table":    {"type": "string", "description": "Fully-qualified table name, e.g. park_ops.tbvw_attendance"},
                    "date_col": {"type": "string", "description": "Date column to group by.  Omit to auto-detect.", "default": "auto"},
                },
                "required": ["table"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_data_freshness",
            "description": "Check when a Delta table was last updated and whether it exceeds its SLA.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table":          {"type": "string"},
                    "max_hours_stale": {"type": "number", "default": 4, "description": "SLA in hours"},
                },
                "required": ["table"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_null_rates",
            "description": "Check null rates for key columns in a table.  Returns columns that exceed the threshold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table":         {"type": "string"},
                    "columns":       {"type": "array", "items": {"type": "string"}, "description": "Columns to check.  Omit to auto-select ID/key columns."},
                    "threshold_pct": {"type": "number", "default": 5, "description": "Alert if null% exceeds this value"},
                },
                "required": ["table"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_schema_drift",
            "description": "Compare the live schema to a known-good column list.  Returns added and removed columns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table":            {"type": "string"},
                    "expected_columns": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["table", "expected_columns"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_cross_table_type_consistency",
            "description": (
                "Check whether a shared column (e.g. 'Voucher ID') has the same "
                "data type across all three primary tables.  Essential for diagnosing "
                "JOIN failures and UNION errors."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "column_name": {"type": "string", "description": "Column name to check (case-insensitive)"},
                    "tables":      {"type": "array", "items": {"type": "string"}, "description": "Tables to compare.  Omit to use the default monitored tables."},
                },
                "required": ["column_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_join_integrity",
            "description": "Count orphaned keys between two tables — records in left_table whose join key has no match in right_table.",
            "parameters": {
                "type": "object",
                "properties": {
                    "left_table":   {"type": "string"},
                    "right_table":  {"type": "string"},
                    "key_column":   {"type": "string"},
                    "sample_date":  {"type": "string", "description": "ISO date (YYYY-MM-DD) to limit the scan.  Omit for full table."},
                },
                "required": ["left_table", "right_table", "key_column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_dq_query",
            "description": "Execute a custom read-only SQL query for ad-hoc data quality investigation.  Results capped at 200 rows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql":         {"type": "string", "description": "SELECT statement only"},
                    "description": {"type": "string", "description": "What this query is investigating"},
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "full_table_health",
            "description": "Quick combined health report for a table: freshness + row-count anomaly in one call.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                },
                "required": ["table"],
            },
        },
    },
]


def run_data_quality_tool(name: str, args: dict) -> str:
    """Dispatch a data quality tool call."""
    handlers = {
        "check_row_count_anomaly":          check_row_count_anomaly,
        "check_data_freshness":             check_data_freshness,
        "check_null_rates":                 check_null_rates,
        "check_schema_drift":               check_schema_drift,
        "check_cross_table_type_consistency": check_cross_table_type_consistency,
        "check_join_integrity":             check_join_integrity,
        "run_dq_query":                     run_dq_query,
        "full_table_health":                full_table_health,
    }
    fn = handlers.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown DQ tool: {name}"})
    try:
        return fn(**args)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
