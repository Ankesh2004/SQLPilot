"""
generate_sql node — takes the user question + schema and produces SQL.

Phase 1: hardcoded schema from SQLite introspection.
Phase 2+: schema comes from RAG retrieval.
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

    reads: user_question, schema_context (or falls back to DB introspection)
    writes: generated_sql, llm_assumptions, sql_dialect
    """
    question = state["user_question"]
    dialect = state.get("sql_dialect", "sqlite")

    # Phase 1: if no schema_context from RAG yet, introspect the DB directly
    schema = state.get("schema_context")
    if not schema:
        db = SQLiteConnector()
        schema = db.get_schema_text()

    llm = get_llm_client()

    system_prompt = SQL_GENERATION_SYSTEM.format(dialect=dialect)
    user_prompt = SQL_GENERATION_USER.format(schema=schema, question=question)

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
