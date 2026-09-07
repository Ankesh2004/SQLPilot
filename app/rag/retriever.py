"""
RAG retriever — takes a user question and returns relevant context
from the vector store.

this is what the generate_sql node calls instead of hardcoded schema.
"""

import logging
from app.rag.store import ChromaStore

logger = logging.getLogger(__name__)


class Retriever:
    """retrieves schema chunks and business rules relevant to a question."""

    def __init__(self, store: ChromaStore | None = None):
        self.store = store or ChromaStore()

    def retrieve(self, question: str, schema_top_k: int = 5, rules_top_k: int = 3) -> dict:
        """
        retrieve relevant context for a question.

        returns a dict with:
            - schema_context: str (joined schema chunks)
            - business_rules_context: str (joined business rules)
            - schema_tables: list[str] (which tables were retrieved)
        """
        # get relevant schema chunks
        schema_results = self.store.query_schema(question, top_k=schema_top_k)
        rules_results = self.store.query_rules(question, top_k=rules_top_k)

        # join schema chunks into a single context string
        schema_parts = []
        schema_tables = []
        for r in schema_results:
            schema_parts.append(r["content"])
            table_name = r["metadata"].get("table_name", "unknown")
            schema_tables.append(table_name)

        schema_context = "\n\n---\n\n".join(schema_parts) if schema_parts else ""

        # join business rules — only include ones that are reasonably relevant
        # chromadb cosine distance: 0 = identical, 2 = opposite
        # we filter out anything above 1.0 (too distant to be useful)
        rules_parts = []
        for r in rules_results:
            distance = r.get("distance", 1.0)
            if distance < 1.0:  # only include if reasonably close
                rules_parts.append(r["content"])

        rules_context = "\n\n---\n\n".join(rules_parts) if rules_parts else ""

        logger.info(
            f"Retrieved {len(schema_parts)} schema chunks "
            f"(tables: {', '.join(schema_tables)}), "
            f"{len(rules_parts)} business rules"
        )

        return {
            "schema_context": schema_context,
            "business_rules_context": rules_context,
            "schema_tables": schema_tables,
        }
