"""
execute_query node — runs the generated SQL against the database.

captures results or errors. runtime errors get stored in correction_history
so the self-correction loop can feed them back to the LLM.
"""

import logging
from app.agents.state import AgentState
from app.db.connection import SQLiteConnector

logger = logging.getLogger(__name__)


def execute_query(state: AgentState) -> dict:
    """
    execute the generated SQL against the demo database.

    reads: generated_sql
    writes: query_results, query_columns, execution_error, correction_history
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

        # classify the error for the correction loop
        is_recoverable = _is_recoverable_error(error_msg)

        # record in correction history
        correction_history = list(state.get("correction_history", []))
        correction_history.append({
            "attempt": len(correction_history) + 1,
            "sql": sql,
            "error_type": "runtime",
            "error_message": error_msg,
            "stage": "execution",
            "recoverable": is_recoverable,
        })

        return {
            "query_results": [],
            "query_columns": [],
            "execution_error": error_msg,
            "correction_history": correction_history,
        }


def _is_recoverable_error(error_msg: str) -> bool:
    """
    classify whether a runtime error is worth retrying.

    per DESIGN.md §7.4.2 — some errors can be fixed by rewriting SQL,
    others are infrastructure problems or impossible queries.
    """
    error_lower = error_msg.lower()

    # recoverable — the LLM can fix these by rewriting
    recoverable_patterns = [
        "no such column",
        "no such table",
        "ambiguous column",
        "syntax error",
        "near \"",
        "misuse of aggregate",
        "wrong number of arguments",
    ]

    for pattern in recoverable_patterns:
        if pattern in error_lower:
            return True

    # unrecoverable — infrastructure or timeout issues
    unrecoverable_patterns = [
        "permission denied",
        "readonly",
        "read-only",
        "timeout",
        "connection",
        "locked",
    ]

    for pattern in unrecoverable_patterns:
        if pattern in error_lower:
            return False

    # default: assume recoverable — better to try than give up
    return True
