"""
SQLite database connector for the demo database.

handles connecting, executing read-only queries, and returning results
as structured data the rest of the pipeline can use.
"""

import sqlite3
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class SQLiteConnector:
    """thin wrapper around sqlite3 for executing generated queries."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.sqlite_db_path
        if not Path(self.db_path).exists():
            raise FileNotFoundError(
                f"Demo database not found at {self.db_path}. "
                "Run 'python scripts/seed_database.py' first."
            )

    def execute_query(self, sql: str) -> dict:
        """
        execute a SQL query and return results.

        returns a dict with:
            - columns: list of column names
            - rows: list of dicts (one per row)
            - row_count: how many rows came back

        raises RuntimeError if the query fails (so the correction loop
        can catch it and feed the error back to the LLM).
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # so we get column names
        cursor = conn.cursor()

        try:
            cursor.execute(sql)
            rows_raw = cursor.fetchmany(settings.max_result_rows)

            if not rows_raw:
                return {"columns": [], "rows": [], "row_count": 0}

            columns = list(rows_raw[0].keys())
            rows = [dict(row) for row in rows_raw]

            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
            }

        except sqlite3.Error as e:
            # wrap in RuntimeError so the pipeline can distinguish
            # DB errors from other exceptions
            raise RuntimeError(f"SQLite error: {e}") from e
        finally:
            conn.close()

    def get_schema_text(self) -> str:
        """
        introspect the database and return a human-readable schema string.

        used in Phase 1 as a hardcoded schema context (before RAG is wired up).
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # get all CREATE TABLE statements — sqlite stores them in sqlite_master
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = cursor.fetchall()
        conn.close()

        schema_parts = []
        for (create_sql,) in tables:
            if create_sql:
                schema_parts.append(create_sql.strip() + ";")

        return "\n\n".join(schema_parts)
