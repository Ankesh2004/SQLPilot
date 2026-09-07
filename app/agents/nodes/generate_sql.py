"""
generate_sql node — takes the user question + schema and produces SQL.

uses schema_context and business_rules_context from the retrieve_context node.
falls back to DB introspection if RAG context isn't available.
"""

import logging
from app.agents.state import AgentState
from app.agents.prompts import SQL_GENERATION_SYSTEM, SQL_GENERATION_USER
from app.llm import get_llm_client
from app.db.connection import SQLiteConnector

logger = logging.getLogger(__name__)


def generate_sql(state: AgentState) -> dict:
    """
    generate a SQL query from the user's natural language question.

    reads: user_question, schema_context, business_rules_context
    writes: generated_sql, llm_assumptions, sql_dialect
    """
    question = state["user_question"]
    dialect = state.get("sql_dialect", "sqlite")

    # schema should come from retrieve_context node (Phase 2+)
    # fallback to DB introspection if somehow missing
    schema = state.get("schema_context")
    if not schema:
        db = SQLiteConnector()
        schema = db.get_schema_text()

    business_rules = state.get("business_rules_context", "")
    if not business_rules:
        business_rules = "(No specific business rules apply to this question)"

    llm = get_llm_client()

    system_prompt = SQL_GENERATION_SYSTEM.format(dialect=dialect)
    user_prompt = SQL_GENERATION_USER.format(
        schema=schema,
        business_rules=business_rules,
        question=question,
    )

    logger.info(f"Generating SQL for: {question}")

    result = llm.generate_structured(user_prompt, system_prompt)

    sql = result.get("sql", "")
    assumptions = result.get("assumptions", "")

    logger.info(f"Generated SQL: {sql}")
    if assumptions:
        logger.info(f"Assumptions: {assumptions}")

    return {
        "generated_sql": sql,
        "llm_assumptions": assumptions,
        "sql_dialect": dialect,
    }
