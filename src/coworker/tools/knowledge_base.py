"""
Knowledge Base Tools
====================
Delta table-backed knowledge base.  Stores articles written by the agent or
by human contributors.  Supports full-text search so the agent can find
relevant context before answering.

Delta table schema:
  article_id      STRING  (UUID)
  category        STRING  (DATA_QUALITY | ONBOARDING | BUSINESS_LOGIC | ETL | SCHEMA)
  title           STRING
  content         STRING  (full Markdown article)
  tags            ARRAY<STRING>
  created_by      STRING
  created_at      TIMESTAMP
  updated_at      TIMESTAMP
  embedding_text  STRING  (title + first 500 chars; used for keyword search)
"""

from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone

from ..config import cfg
from ..db_client import get_db

_KB_TABLE = f"{cfg.AGENT_CATALOG}.{cfg.AGENT_SCHEMA}.knowledge_base"


def _ensure_table() -> None:
    """Create the knowledge base table if it doesn't exist."""
    db = get_db()
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS {_KB_TABLE} (
            article_id      STRING,
            category        STRING,
            title           STRING,
            content         STRING,
            tags            ARRAY<STRING>,
            created_by      STRING,
            created_at      TIMESTAMP,
            updated_at      TIMESTAMP,
            embedding_text  STRING
        )
        USING DELTA
        TBLPROPERTIES ('delta.autoOptimize.optimizeWrite' = 'true')
    """)


# ── CRUD ───────────────────────────────────────────────────────────────────

def save_article(
    title: str,
    content: str,
    category: str = "GENERAL",
    tags: list[str] | None = None,
    created_by: str = "co-worker-agent",
) -> str:
    _ensure_table()
    db = get_db()

    now = datetime.now(timezone.utc)
    article_id = str(uuid.uuid4())
    embedding_text = f"{title}. {content[:500]}"

    tags_sql = "ARRAY(" + ", ".join(f"'{t}'" for t in (tags or [])) + ")"
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    db.execute(f"""
        INSERT INTO {_KB_TABLE}
        (article_id, category, title, content, tags, created_by, created_at, updated_at, embedding_text)
        VALUES (
            '{article_id}',
            '{category.upper()}',
            '{title.replace("'", "''")}',
            '{content.replace("'", "''")}',
            {tags_sql},
            '{created_by.replace("'", "''")}',
            TIMESTAMP '{now_str}',
            TIMESTAMP '{now_str}',
            '{embedding_text.replace("'", "''")}'
        )
    """)

    return json.dumps({
        "status": "saved",
        "article_id": article_id,
        "title": title,
        "table": _KB_TABLE,
    })


def search_articles(query: str, category: str | None = None, limit: int = 5) -> str:
    """
    Full-text search over titles and embedding_text.
    Databricks Runtime 13+ supports CONTAINS / LIKE; we use LIKE for broadest compatibility.
    """
    _ensure_table()
    db = get_db()

    terms = [t.strip() for t in query.lower().split() if len(t.strip()) > 2]
    if not terms:
        return json.dumps({"error": "Query too short.  Provide at least one meaningful keyword."})

    # Build a WHERE clause: all terms must appear in title OR embedding_text
    conditions = " AND ".join(
        f"(LOWER(title) LIKE '%{t}%' OR LOWER(embedding_text) LIKE '%{t}%')"
        for t in terms[:5]  # cap to 5 terms
    )
    cat_filter = f"AND category = '{category.upper()}'" if category else ""

    articles = db.execute(f"""
        SELECT article_id, category, title, LEFT(content, 600) AS excerpt,
               tags, created_by, updated_at
        FROM {_KB_TABLE}
        WHERE {conditions} {cat_filter}
        ORDER BY updated_at DESC
        LIMIT {limit}
    """)

    return json.dumps({
        "query": query,
        "results_found": len(articles),
        "articles": articles,
    }, default=str)


def get_article(article_id: str) -> str:
    """Retrieve a full article by ID."""
    _ensure_table()
    db = get_db()
    rows = db.execute(
        f"SELECT * FROM {_KB_TABLE} WHERE article_id = '{article_id}'"
    )
    if not rows:
        return json.dumps({"error": f"Article '{article_id}' not found."})
    return json.dumps(rows[0], default=str)


def list_articles(category: str | None = None, limit: int = 20) -> str:
    """List article titles and IDs, optionally filtered by category."""
    _ensure_table()
    db = get_db()
    cat_filter = f"WHERE category = '{category.upper()}'" if category else ""
    articles = db.execute(f"""
        SELECT article_id, category, title, tags, updated_at
        FROM {_KB_TABLE}
        {cat_filter}
        ORDER BY updated_at DESC
        LIMIT {limit}
    """)
    return json.dumps({
        "total": len(articles),
        "articles": articles,
    }, default=str)


# ── OpenAI tool schemas ────────────────────────────────────────────────────

KNOWLEDGE_BASE_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "save_article",
            "description": (
                "Write a new knowledge-base article to the Delta table.  Use this "
                "to document data quality findings, business logic explanations, "
                "onboarding guides, or ETL patterns so they are reusable by the "
                "team and future conversations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title":      {"type": "string"},
                    "content":    {"type": "string", "description": "Full Markdown article"},
                    "category":   {
                        "type": "string",
                        "enum": ["DATA_QUALITY", "ONBOARDING", "BUSINESS_LOGIC", "ETL", "SCHEMA", "GENERAL"],
                        "default": "GENERAL",
                    },
                    "tags":       {"type": "array", "items": {"type": "string"}},
                    "created_by": {"type": "string", "default": "co-worker-agent"},
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_articles",
            "description": "Search the knowledge base for articles matching a query.  Call this BEFORE answering any question — you may already have a documented answer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query":    {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": ["DATA_QUALITY", "ONBOARDING", "BUSINESS_LOGIC", "ETL", "SCHEMA", "GENERAL"],
                        "description": "Filter by category.  Omit to search all.",
                    },
                    "limit":    {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_article",
            "description": "Retrieve the full content of a knowledge-base article by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "article_id": {"type": "string"},
                },
                "required": ["article_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_articles",
            "description": "List all knowledge-base articles, optionally filtered by category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": ["DATA_QUALITY", "ONBOARDING", "BUSINESS_LOGIC", "ETL", "SCHEMA", "GENERAL"]},
                    "limit":    {"type": "integer", "default": 20},
                },
            },
        },
    },
]


def run_knowledge_base_tool(name: str, args: dict) -> str:
    handlers = {
        "save_article":    save_article,
        "search_articles": search_articles,
        "get_article":     get_article,
        "list_articles":   list_articles,
    }
    fn = handlers.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown KB tool: {name}"})
    try:
        return fn(**args)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
