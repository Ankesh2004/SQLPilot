"""
Schema introspection — reads the database structure and produces
chunked text documents ready for embedding.

one document per table, including column names, types, foreign keys,
and sample values for low-cardinality columns.
"""

import sqlite3
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def introspect_sqlite(db_path: str | None = None) -> list[dict]:
    """
    introspect the SQLite database and produce one document per table.

    each document is a dict with:
        - table_name: str
        - content: str (human-readable schema description)
        - metadata: dict (table_name, column_count, etc.)

    the content is what gets embedded and retrieved.
    """
    db_path = db_path or settings.sqlite_db_path
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # get all table names
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    tables = [row[0] for row in cursor.fetchall()]

    documents = []
    for table in tables:
        doc = _build_table_document(cursor, table)
        documents.append(doc)
        logger.info(f"Introspected table '{table}': {doc['metadata']['column_count']} columns")

    conn.close()
    return documents


def _build_table_document(cursor, table_name: str) -> dict:
    """build a rich text document for a single table."""

    # get column info
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    # columns: (cid, name, type, notnull, default_value, pk)

    # get foreign keys
    cursor.execute(f"PRAGMA foreign_key_list({table_name})")
    fks = cursor.fetchall()
    # fks: (id, seq, table, from, to, on_update, on_delete, match)

    # build the text content
    lines = [f"Table: {table_name}"]
    lines.append(f"Description: Contains {table_name.replace('_', ' ')} data")
    lines.append("")
    lines.append("Columns:")

    for col in columns:
        cid, name, col_type, notnull, default, pk = col
        parts = [f"  - {name} ({col_type or 'TEXT'})"]
        if pk:
            parts.append("[PRIMARY KEY]")
        if notnull:
            parts.append("[NOT NULL]")
        if default is not None:
            parts.append(f"[DEFAULT: {default}]")
        lines.append(" ".join(parts))

        # grab sample values for columns that look categorical
        # (CHECK constraints or low cardinality)
        samples = _get_sample_values(cursor, table_name, name)
        if samples:
            lines.append(f"    Possible values: {', '.join(repr(s) for s in samples)}")

    if fks:
        lines.append("")
        lines.append("Foreign Keys:")
        for fk in fks:
            lines.append(f"  - {fk[3]} → {fk[2]}.{fk[4]}")

    # row count for context
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    row_count = cursor.fetchone()[0]
    lines.append("")
    lines.append(f"Row count: {row_count}")

    content = "\n".join(lines)

    return {
        "table_name": table_name,
        "content": content,
        "metadata": {
            "table_name": table_name,
            "column_count": len(columns),
            "row_count": row_count,
            "type": "schema",
        },
    }


def _get_sample_values(cursor, table_name: str, column_name: str, max_distinct: int = 15) -> list:
    """
    get distinct values for a column if it's low-cardinality.

    only returns values if there are <= max_distinct distinct values.
    this helps the LLM know valid filter values (e.g., plan_type, status, etc.)
    """
    try:
        cursor.execute(
            f"SELECT DISTINCT {column_name} FROM {table_name} "
            f"WHERE {column_name} IS NOT NULL "
            f"LIMIT {max_distinct + 1}"
        )
        values = [row[0] for row in cursor.fetchall()]

        # only return if genuinely low-cardinality
        if len(values) <= max_distinct:
            return sorted(values, key=str)
        return []
    except Exception:
        return []
