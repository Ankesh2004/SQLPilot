"""
SQLite database connector for the demo database.

handles connecting, executing read-only queries, and returning results
as structured data the rest of the pipeline can use.

security hardening (Phase 6):
  - read-only connection via query_only pragma
  - statement timeout via interrupt after N seconds
  - row limit via fetchmany (configurable in settings)
"""

import sqlite3
import logging
import threading
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
        execute a SQL query in a read-only, time-limited sandbox.

        returns a dict with:
            - columns: list of column names
            - rows: list of dicts (one per row)
            - row_count: how many rows came back

        raises RuntimeError if the query fails, times out, or is blocked.
        """
        timeout_s = settings.statement_timeout_ms / 1000.0

        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row

        try:
            # enforce read-only mode at the SQLite level
            # this prevents any writes even if our blocklist somehow misses something
            conn.execute("PRAGMA query_only = ON")

            # set up a timer to interrupt long-running queries
            timer = threading.Timer(timeout_s, conn.interrupt)
            timer.start()

            try:
                cursor = conn.cursor()
                cursor.execute(sql)
                rows_raw = cursor.fetchmany(settings.max_result_rows)
            finally:
                timer.cancel()

            if not rows_raw:
                return {"columns": [], "rows": [], "row_count": 0}

            columns = list(rows_raw[0].keys())
            rows = [dict(row) for row in rows_raw]

            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
            }

        except sqlite3.OperationalError as e:
            error_msg = str(e)
            # sqlite3.interrupt() raises "interrupted" — translate to timeout
            if "interrupted" in error_msg.lower():
                raise RuntimeError(
                    f"Query timed out after {timeout_s}s. "
                    "Try simplifying the query or adding filters to reduce the result set."
                ) from e
            # read-only violation
            if "readonly" in error_msg.lower() or "query_only" in error_msg.lower():
                raise RuntimeError(
                    "Query was blocked: only SELECT queries are allowed. "
                    "The database is in read-only mode."
                ) from e
            raise RuntimeError(f"SQLite error: {e}") from e

        except sqlite3.Error as e:
            raise RuntimeError(f"SQLite error: {e}") from e

        finally:
            conn.close()

    def get_schema_text(self) -> str:
        """
        introspect the database and return a human-readable schema string.

        used as fallback schema context when RAG isn't available.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

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
