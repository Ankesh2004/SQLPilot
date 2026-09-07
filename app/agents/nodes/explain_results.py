"""
explain_results node — takes query results and explains them in plain English.
"""

import json
import logging
from app.agents.state import AgentState
from app.agents.prompts import EXPLAIN_SYSTEM, EXPLAIN_USER
from app.llm import get_llm_client

logger = logging.getLogger(__name__)


def explain_results(state: AgentState) -> dict:
    """
    generate a plain-English explanation of the query results.

    reads: user_question, query_results, query_columns
    writes: explanation, final_status
    """
    question = state["user_question"]
    results = state.get("query_results", [])
    columns = state.get("query_columns", [])

    # if execution failed, explain the error instead
    exec_error = state.get("execution_error", "")
    if exec_error:
        return {
            "explanation": f"The query failed to execute: {exec_error}",
            "final_status": "error",
        }

    # format a preview of the results for the LLM
    preview_rows = results[:20]  # don't dump 1000 rows into the prompt
    if preview_rows:
        results_preview = json.dumps(preview_rows, indent=2, default=str)
    else:
        results_preview = "(no results)"

    llm = get_llm_client()

    user_prompt = EXPLAIN_USER.format(
        question=question,
        row_count=len(results),
        columns=", ".join(columns) if columns else "none",
        results_preview=results_preview,
    )

    explanation = llm.generate(user_prompt, EXPLAIN_SYSTEM)

    logger.info(f"Explanation generated ({len(explanation)} chars)")

    return {
        "explanation": explanation,
        "final_status": "success",
    }
