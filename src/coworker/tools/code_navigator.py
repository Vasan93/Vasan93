"""
Code Navigator Tools
====================
Let the agent explore Databricks notebooks, Python files, and SQL scripts in
the workspace.  Uses the Databricks Workspace API to list and read notebooks,
and Spark to query INFORMATION_SCHEMA for live table/view definitions.
"""

from __future__ import annotations
import json
import re

from ..config import cfg


def _spark():
    from pyspark.sql import SparkSession
    s = SparkSession.getActiveSession()
    if s is None:
        raise RuntimeError("No active SparkSession.")
    return s


def _dbutils():
    try:
        from databricks.sdk.runtime import dbutils
        return dbutils
    except Exception:
        raise RuntimeError("dbutils not available — run inside Databricks.")


# ── Tool: list notebooks in a workspace path ──────────────────────────────

def list_notebooks(path: str = "/Repos", recursive: bool = False) -> str:
    """List notebooks and files under a workspace path."""
    du = _dbutils()
    try:
        items = du.fs.ls(f"dbfs:{path}") if path.startswith("/dbfs") else []
        # Use workspace API via notebook utilities
        items = du.notebook.entry_point.getDbutils().notebook().getContext().toJson()
    except Exception:
        pass

    # Fallback: use the REST API through dbutils
    try:
        import requests
        ctx = json.loads(
            du.notebook.entry_point.getDbutils().notebook().getContext().toJson()
        )
        host = ctx.get("extraContext", {}).get("api_url", "")
        token = ctx.get("extraContext", {}).get("api_token", "")

        resp = requests.get(
            f"{host}/api/2.0/workspace/list",
            headers={"Authorization": f"Bearer {token}"},
            json={"path": path},
            timeout=10,
        )
        resp.raise_for_status()
        objects = resp.json().get("objects", [])

        results = []
        for obj in objects:
            results.append({
                "path": obj.get("path"),
                "type": obj.get("object_type"),  # NOTEBOOK, DIRECTORY, FILE
                "language": obj.get("language"),
            })

        if recursive:
            for obj in objects:
                if obj.get("object_type") == "DIRECTORY":
                    sub = json.loads(list_notebooks(obj["path"], recursive=True))
                    results.extend(sub.get("items", []))

        return json.dumps({"path": path, "count": len(results), "items": results})
    except Exception as exc:
        return json.dumps({"error": f"Could not list workspace path: {exc}"})


# ── Tool: read a notebook or file ────────────────────────────────────────

def read_notebook(path: str) -> str:
    """
    Export and return the content of a Databricks notebook.
    Returns source code as a string (useful for the LLM to reason over).
    """
    try:
        import requests
        du = _dbutils()
        ctx = json.loads(
            du.notebook.entry_point.getDbutils().notebook().getContext().toJson()
        )
        host = ctx.get("extraContext", {}).get("api_url", "")
        token = ctx.get("extraContext", {}).get("api_token", "")

        resp = requests.get(
            f"{host}/api/2.0/workspace/export",
            headers={"Authorization": f"Bearer {token}"},
            params={"path": path, "format": "SOURCE"},
            timeout=15,
        )
        resp.raise_for_status()
        import base64
        content = base64.b64decode(resp.json().get("content", "")).decode("utf-8")

        # Truncate very long notebooks for the LLM context window
        if len(content) > 15_000:
            content = content[:15_000] + "\n\n... [truncated — first 15 000 chars shown]"

        return json.dumps({
            "path": path,
            "char_count": len(content),
            "content": content,
        })
    except Exception as exc:
        return json.dumps({"error": f"Could not read notebook: {exc}"})


# ── Tool: describe a table/view schema ───────────────────────────────────

def describe_table(table: str) -> str:
    """
    Return the full schema (columns, types, comments) of a Delta table or
    Snowflake view via DESCRIBE TABLE EXTENDED.
    """
    spark = _spark()
    safe = table.strip()
    if not re.fullmatch(r"[\w.]+", safe):
        return json.dumps({"error": f"Invalid table name: {safe}"})

    try:
        rows = spark.sql(f"DESCRIBE TABLE EXTENDED {safe}").collect()
        columns = []
        metadata = {}
        in_metadata = False

        for row in rows:
            d = row.asDict()
            col_name = (d.get("col_name") or "").strip()
            data_type = (d.get("data_type") or "").strip()

            if col_name == "" and data_type == "":
                in_metadata = True
                continue
            if col_name.startswith("#"):
                continue

            if in_metadata:
                metadata[col_name] = data_type
            else:
                columns.append({
                    "name": col_name,
                    "type": data_type,
                    "comment": (d.get("comment") or "").strip(),
                })

        return json.dumps({
            "table": safe,
            "column_count": len(columns),
            "columns": columns,
            "metadata": metadata,
        }, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── Tool: search SQL in notebooks / information_schema ───────────────────

def search_code(keyword: str, catalog: str | None = None) -> str:
    """
    Search for a keyword across table/column names in INFORMATION_SCHEMA.
    Useful for finding where a business concept lives in the warehouse.
    """
    spark = _spark()
    cat = catalog or cfg.AGENT_CATALOG

    try:
        # Search column names
        col_rows = spark.sql(f"""
            SELECT table_catalog, table_schema, table_name, column_name, data_type
            FROM {cat}.information_schema.columns
            WHERE LOWER(column_name) LIKE '%{keyword.lower()}%'
            ORDER BY table_schema, table_name, ordinal_position
            LIMIT 50
        """).collect()

        # Search table names
        tbl_rows = spark.sql(f"""
            SELECT table_catalog, table_schema, table_name, table_type
            FROM {cat}.information_schema.tables
            WHERE LOWER(table_name) LIKE '%{keyword.lower()}%'
            LIMIT 20
        """).collect()

        return json.dumps({
            "keyword": keyword,
            "matching_columns": [r.asDict() for r in col_rows],
            "matching_tables":  [r.asDict() for r in tbl_rows],
        }, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── Tool: explain table lineage ──────────────────────────────────────────

def explain_table_lineage(table: str) -> str:
    """
    Retrieve Delta table history (last 20 operations) to understand how the
    table is populated: who writes to it, how often, what operations.
    """
    spark = _spark()
    safe = table.strip()
    if not re.fullmatch(r"[\w.]+", safe):
        return json.dumps({"error": f"Invalid table name: {safe}"})

    try:
        rows = spark.sql(f"DESCRIBE HISTORY {safe} LIMIT 20").collect()
        history = []
        for r in rows:
            d = r.asDict()
            history.append({
                "version": d.get("version"),
                "timestamp": str(d.get("timestamp")),
                "operation": d.get("operation"),
                "user": d.get("userName"),
                "parameters": d.get("operationParameters"),
                "metrics": d.get("operationMetrics"),
            })
        return json.dumps({
            "table": safe,
            "history_entries": len(history),
            "history": history,
        }, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── OpenAI tool schemas ──────────────────────────────────────────────────

CODE_NAVIGATOR_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_notebooks",
            "description": "List notebooks and files under a Databricks workspace path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":      {"type": "string", "default": "/Repos", "description": "Workspace path to list"},
                    "recursive": {"type": "boolean", "default": False},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_notebook",
            "description": "Read the source code of a Databricks notebook.  Use this to understand ETL logic, business rules, or pipeline code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Workspace path, e.g. /Repos/team/project/etl_attendance"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describe_table",
            "description": "Get the full schema of a table or view — column names, data types, and comments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "Fully-qualified table name"},
                },
                "required": ["table"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": (
                "Search for a keyword across all column and table names in the "
                "catalog's INFORMATION_SCHEMA.  Use this to find where a business "
                "concept (e.g. 'voucher', 'promotion', 'annual pass') lives in the "
                "data warehouse."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "catalog": {"type": "string", "description": "Catalog to search.  Omit to use the default."},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_table_lineage",
            "description": "Show Delta table history — last 20 operations, who ran them, what changed.  Helps understand ETL frequency and ownership.",
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


def run_code_navigator_tool(name: str, args: dict) -> str:
    handlers = {
        "list_notebooks":       list_notebooks,
        "read_notebook":        read_notebook,
        "describe_table":       describe_table,
        "search_code":          search_code,
        "explain_table_lineage": explain_table_lineage,
    }
    fn = handlers.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown code navigator tool: {name}"})
    try:
        return fn(**args)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
