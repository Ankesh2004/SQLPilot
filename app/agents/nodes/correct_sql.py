"""
correct_sql node — asks the LLM to fix a SQL query based on error feedback.

this is the core of the self-correction loop. it gets called when:
  - SQLGlot validation fails (syntax errors)
  - database execution fails (runtime errors like missing columns)

it feeds the full error history to the LLM so it doesn't repeat mistakes.
"""

import logging
from app.agents.state import AgentState
from app.agents.prompts_correction import SQL_CORRECTION_SYSTEM, SQL_CORRECTION_USER
from app.llm import get_llm_client

logger = logging.getLogger(__name__)


def correct_sql(state: AgentState) -> dict:
    """
    ask the LLM to fix a failed SQL query.

    reads: user_question, clarified_question, schema_context, business_rules_context,
           correction_history, sql_dialect, validation_retry_count, execution_retry_count
    writes: generated_sql, llm_assumptions, validation_retry_count or execution_retry_count
    """
    question = state.get("clarified_question") or state["user_question"]
    schema = state.get("schema_context", "")
    rules = state.get("business_rules_context", "")
    dialect = state.get("sql_dialect", "sqlite")
    history = state.get("correction_history", [])

    # figure out which retry counter to bump based on the last error's stage
    last_error = history[-1] if history else {}
    stage = last_error.get("stage", "validation")

    if stage == "validation":
        retry_count = state.get("validation_retry_count", 0) + 1
        counter_update = {"validation_retry_count": retry_count}
    else:
        retry_count = state.get("execution_retry_count", 0) + 1
        counter_update = {"execution_retry_count": retry_count}

    # format error history for the prompt
    history_text = _format_error_history(history)

    llm = get_llm_client()

    system_prompt = SQL_CORRECTION_SYSTEM.format(dialect=dialect)
    user_prompt = SQL_CORRECTION_USER.format(
        question=question,
        schema=schema,
        business_rules=rules,
        error_history=history_text,
    )

    logger.info(f"Correction attempt (stage={stage}, retry={retry_count})")

    result = llm.generate_structured(user_prompt, system_prompt)

    sql = result.get("sql", "")
    assumptions = result.get("assumptions", "")
    what_changed = result.get("what_i_changed", "")

    logger.info(f"Corrected SQL: {sql}")
    if what_changed:
        logger.info(f"What changed: {what_changed}")

    return {
        "generated_sql": sql,
        "llm_assumptions": assumptions,
        # reset validation state so the corrected SQL gets re-validated
        "validation_passed": False,
        "validation_error": "",
        "execution_error": "",
        **counter_update,
    }


def _format_error_history(history: list[dict]) -> str:
    """format the correction history into a readable string for the prompt."""
    if not history:
        return "(No previous attempts)"

    parts = []
    for entry in history:
        attempt = entry.get("attempt", "?")
        sql = entry.get("sql", "")
        error = entry.get("error_message", "")
        stage = entry.get("stage", "")
        parts.append(
            f"Attempt {attempt} ({stage}):\n"
            f"  SQL: {sql}\n"
            f"  Error: {error}"
        )

    return "\n\n".join(parts)
