"""
execute_query node — runs the generated SQL against the database.

captures results or errors. errors get stored in state so the
correction loop (Phase 4) can feed them back to the LLM.
"""

import logging
from app.agents.state import AgentState
from app.db.connection import SQLiteConnector

logger = logging.getLogger(__name__)


def execute_query(state: AgentState) -> dict:
    """
    execute the generated SQL against the demo database.

    reads: generated_sql
    writes: query_results, query_columns, execution_error, final_status
    """
    sql = state.get("generated_sql", "")
    if not sql:
        return {
            "execution_error": "No SQL query to execute",
            "final_status": "error",
        }

    db = SQLiteConnector()

    try:
        result = db.execute_query(sql)

        logger.info(f"Query returned {result['row_count']} rows")

        return {
            "query_results": result["rows"],
            "query_columns": result["columns"],
            "execution_error": "",  # clear any previous error
        }

    except RuntimeError as e:
        error_msg = str(e)
        logger.warning(f"Query execution failed: {error_msg}")

        return {
            "query_results": [],
            "query_columns": [],
            "execution_error": error_msg,
        }
