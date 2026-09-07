"""
retrieve_context node — pulls relevant schema + business rules from ChromaDB.

runs before generate_sql so the LLM has the right context.
falls back to full DB introspection if ChromaDB isn't indexed yet.
"""

import logging
from app.agents.state import AgentState
from app.db.connection import SQLiteConnector

logger = logging.getLogger(__name__)


def retrieve_context(state: AgentState) -> dict:
    """
    retrieve relevant schema chunks and business rules for the user's question.

    reads: user_question
    writes: schema_context, business_rules_context
    """
    question = state["user_question"]

    try:
        from app.rag.retriever import Retriever
        retriever = Retriever()

        result = retriever.retrieve(question)

        schema_context = result["schema_context"]
        rules_context = result["business_rules_context"]

        # if retrieval returned nothing (empty index), fall back
        if not schema_context:
            logger.warning("RAG returned empty schema context, falling back to introspection")
            db = SQLiteConnector()
            schema_context = db.get_schema_text()

        return {
            "schema_context": schema_context,
            "business_rules_context": rules_context,
        }

    except Exception as e:
        # ChromaDB not indexed yet, or some other error — fall back gracefully
        logger.warning(f"RAG retrieval failed ({e}), falling back to DB introspection")
        db = SQLiteConnector()
        return {
            "schema_context": db.get_schema_text(),
            "business_rules_context": "",
        }
