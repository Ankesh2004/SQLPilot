"""
Index schema + knowledge base into ChromaDB for RAG retrieval.

Run after seed_database.py:
    python scripts/index_rag.py

Built out properly in Phase 2. This is the placeholder.
"""

# TODO (Phase 2): implement schema introspection + embedding pipeline
# - connect to SQLite demo DB
# - introspect all tables/columns/types/FKs
# - generate schema chunks (one per table)
# - read knowledge_base/*.md files
# - embed everything with sentence-transformers (all-MiniLM-L6-v2)
# - store in ChromaDB (two collections: schema_chunks, business_rules)

if __name__ == "__main__":
    print("[SKIP] RAG indexing not yet implemented (Phase 2)")
    print("   For now, the demo database is ready at data/demo.db")
