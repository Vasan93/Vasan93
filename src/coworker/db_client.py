"""
Database Client — abstracts SparkSession vs Databricks SQL Connector
=====================================================================
On a Databricks cluster  → uses SparkSession (full Spark, Delta, DESCRIBE HISTORY)
On Databricks Apps / external → uses databricks-sql-connector (serverless SQL Warehouse)

The rest of the codebase calls `db.execute(sql)` and `db.get_columns(table)` — it
never needs to know which backend is in use.

Configuration:
  Set SQL_WAREHOUSE_PATH in Databricks secrets or env to use SQL Connector mode.
  If not set, falls back to SparkSession (cluster mode).

  Example SQL_WAREHOUSE_PATH: /sql/1.0/warehouses/abc123def456
"""

from __future__ import annotations
import json
import logging
import re
from typing import Any

from .config import cfg

log = logging.getLogger("coworker.db")

# ── Public interface ──────────────────────────────────────────────────────

_client: "_DBClient | None" = None


def get_db() -> "_DBClient":
    """Get the singleton database client (auto-detects Spark vs SQL Connector)."""
    global _client
    if _client is None:
        _client = _create_client()
    return _client


class _DBClient:
    """Unified interface for running SQL and inspecting schemas."""

    def execute(self, sql: str, limit: int = 10_000) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_columns(self, table: str) -> list[dict[str, str]]:
        """Return [{"name": ..., "type": ..., "comment": ...}, ...]"""
        raise NotImplementedError

    def table_exists(self, table: str) -> bool:
        raise NotImplementedError

    @property
    def mode(self) -> str:
        raise NotImplementedError


# ── SparkSession backend (cluster mode) ───────────────────────────────────

class _SparkClient(_DBClient):

    def __init__(self):
        from pyspark.sql import SparkSession
        self._spark = SparkSession.getActiveSession()
        if self._spark is None:
            raise RuntimeError("No active SparkSession.")
        log.info("DB client: SparkSession mode")

    @property
    def mode(self) -> str:
        return "spark"

    def execute(self, sql: str, limit: int = 10_000) -> list[dict[str, Any]]:
        rows = self._spark.sql(sql).limit(limit).collect()
        return [r.asDict() for r in rows]

    def get_columns(self, table: str) -> list[dict[str, str]]:
        _validate_table(table)
        schema = self._spark.table(table).schema
        return [
            {"name": c.name, "type": str(c.dataType), "comment": ""}
            for c in schema
        ]

    def table_exists(self, table: str) -> bool:
        _validate_table(table)
        try:
            self._spark.table(table)
            return True
        except Exception:
            return False


# ── Databricks SQL Connector backend (serverless / Apps mode) ─────────────

class _SQLConnectorClient(_DBClient):

    def __init__(self):
        from databricks import sql as dbsql
        self._connect_args = dict(
            server_hostname=cfg.DATABRICKS_HOST,
            http_path=cfg.SQL_WAREHOUSE_PATH,
            access_token=cfg.DATABRICKS_TOKEN,
        )
        # Test connectivity
        with dbsql.connect(**self._connect_args) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        log.info("DB client: SQL Connector mode (warehouse: %s)", cfg.SQL_WAREHOUSE_PATH)

    @property
    def mode(self) -> str:
        return "sql_connector"

    def execute(self, sql: str, limit: int = 10_000) -> list[dict[str, Any]]:
        from databricks import sql as dbsql
        with dbsql.connect(**self._connect_args) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                columns = [desc[0] for desc in cur.description] if cur.description else []
                rows = cur.fetchmany(limit)
                return [dict(zip(columns, row)) for row in rows]

    def get_columns(self, table: str) -> list[dict[str, str]]:
        _validate_table(table)
        rows = self.execute(f"DESCRIBE TABLE {table}")
        columns = []
        for row in rows:
            col_name = (row.get("col_name") or "").strip()
            data_type = (row.get("data_type") or "").strip()
            if col_name and not col_name.startswith("#") and data_type:
                columns.append({
                    "name": col_name,
                    "type": data_type,
                    "comment": (row.get("comment") or "").strip(),
                })
        return columns

    def table_exists(self, table: str) -> bool:
        _validate_table(table)
        try:
            self.execute(f"DESCRIBE TABLE {table}", limit=1)
            return True
        except Exception:
            return False


# ── Factory ───────────────────────────────────────────────────────────────

def _create_client() -> _DBClient:
    """Auto-detect the best backend."""
    # 1. If SQL Warehouse is configured, prefer it (works everywhere)
    if cfg.SQL_WAREHOUSE_PATH:
        try:
            return _SQLConnectorClient()
        except Exception as exc:
            log.warning("SQL Connector failed (%s), trying SparkSession...", exc)

    # 2. Try SparkSession (only works on a cluster)
    try:
        return _SparkClient()
    except Exception:
        pass

    # 3. Last resort: require SQL Warehouse
    raise RuntimeError(
        "No database backend available.  Either:\n"
        "  - Run on a Databricks cluster (SparkSession), or\n"
        "  - Set SQL_WAREHOUSE_PATH in secrets/env to use a SQL Warehouse."
    )


def _validate_table(name: str) -> None:
    if not re.fullmatch(r"[\w.]+", name.strip()):
        raise ValueError(f"Invalid table name: '{name}'")
