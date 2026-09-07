"""
Full RAG indexing pipeline — introspect DB + read knowledge base + embed into ChromaDB.

Run this to (re-)index everything:
    python scripts/index_rag.py
"""

import sys
import logging
from pathlib import Path

# make sure we can import the app package when running this script directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.rag.schema_introspector import introspect_sqlite
from app.rag.store import ChromaStore
from app.config import settings

logger = logging.getLogger(__name__)

KNOWLEDGE_BASE_DIR = Path(__file__).parent.parent / "knowledge_base"


def load_knowledge_base() -> list[dict]:
    """read all markdown files from knowledge_base/ and prepare them for indexing."""
    docs = []
    if not KNOWLEDGE_BASE_DIR.exists():
        logger.warning(f"Knowledge base directory not found: {KNOWLEDGE_BASE_DIR}")
        return docs

    for md_file in sorted(KNOWLEDGE_BASE_DIR.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        name = md_file.stem  # filename without extension

        docs.append({
            "name": name,
            "content": content,
            "metadata": {
                "source_file": md_file.name,
                "metric_name": name,
                "type": "business_rule",
            },
        })
        logger.info(f"Loaded knowledge base: {md_file.name} ({len(content)} chars)")

    return docs


def run_indexing():
    """run the full indexing pipeline."""

    print("[1/3] Introspecting database schema...")
    schema_docs = introspect_sqlite()
    for doc in schema_docs:
        print(f"  - {doc['table_name']}: {doc['metadata']['column_count']} columns, {doc['metadata']['row_count']} rows")

    print(f"\n[2/3] Loading knowledge base from {KNOWLEDGE_BASE_DIR}...")
    rules_docs = load_knowledge_base()
    for doc in rules_docs:
        print(f"  - {doc['name']}.md ({len(doc['content'])} chars)")

    print("\n[3/3] Indexing into ChromaDB...")
    store = ChromaStore()

    schema_count = store.index_schema_docs(schema_docs)
    rules_count = store.index_business_rules(rules_docs)

    print(f"\n[OK] Indexed {schema_count} schema chunks + {rules_count} business rules")
    print(f"     ChromaDB data stored at: {settings.chroma_persist_dir}")

    # quick sanity check — query for something and see what comes back
    print("\n--- Sanity check ---")
    test_queries = [
        "What is our MRR?",
        "Show me customer details",
        "How many support tickets are open?",
    ]
    for q in test_queries:
        schema_results = store.query_schema(q, top_k=3)
        rules_results = store.query_rules(q, top_k=2)
        schema_tables = [r["metadata"].get("table_name", "?") for r in schema_results]
        rule_names = [r["metadata"].get("metric_name", "?") for r in rules_results if r.get("distance", 1.0) < 1.0]
        print(f'  "{q}"')
        print(f"    -> schema: {schema_tables}")
        print(f"    -> rules: {rule_names if rule_names else '(none relevant)'}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    run_indexing()
