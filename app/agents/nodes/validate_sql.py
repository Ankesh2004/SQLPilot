"""
validate_sql node — runs SQLGlot validation + security blocklist on generated SQL.

sits between generate_sql and execute_query. catches syntax errors and
dangerous queries before they hit the database.
"""

import logging
from app.agents.state import AgentState
from app.validation import validate_sql

logger = logging.getLogger(__name__)


def validate_sql_node(state: AgentState) -> dict:
    """
    validate the generated SQL using SQLGlot.

    reads: generated_sql, sql_dialect
    writes: validation_error, validation_error_type, validation_passed
    """
    sql = state.get("generated_sql", "")
    dialect = state.get("sql_dialect", "sqlite")

    result = validate_sql(sql, dialect)

    if result.is_valid:
        logger.info("SQL validation passed")
        return {
            "validation_passed": True,
            "validation_error": "",
            "validation_error_type": "",
        }

    logger.warning(f"SQL validation failed ({result.error_type}): {result.error_message}")

    # record this in correction history
    correction_history = list(state.get("correction_history", []))
    correction_history.append({
        "attempt": len(correction_history) + 1,
        "sql": sql,
        "error_type": result.error_type,
        "error_message": result.error_message,
        "stage": "validation",
        "recoverable": result.is_recoverable,
    })

    return {
        "validation_passed": False,
        "validation_error": result.error_message,
        "validation_error_type": result.error_type,
        "correction_history": correction_history,
    }
