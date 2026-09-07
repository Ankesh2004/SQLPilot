"""
ChromaDB wrapper — manages collections and handles embedding + storage.

two collections:
  - schema_chunks: one doc per database table
  - business_rules: one doc per knowledge base markdown file
"""

import logging
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings

logger = logging.getLogger(__name__)


class ChromaStore:
    """manages ChromaDB collections for schema and business rules."""

    def __init__(self, persist_dir: str | None = None):
        persist_dir = persist_dir or settings.chroma_persist_dir
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # we use ChromaDB's built-in sentence-transformer embedding
        # so we don't need to manage the model ourselves
        self.schema_collection = self.client.get_or_create_collection(
            name="schema_chunks",
            metadata={"hnsw:space": "cosine"},
        )
        self.rules_collection = self.client.get_or_create_collection(
            name="business_rules",
            metadata={"hnsw:space": "cosine"},
        )

    def index_schema_docs(self, documents: list[dict]) -> int:
        """
        index schema documents into the schema_chunks collection.

        each doc should have: table_name, content, metadata
        clears existing docs first (full re-index).
        """
        # wipe and re-index — schema changes should fully replace old data
        existing = self.schema_collection.count()
        if existing > 0:
            # get all ids and delete them
            all_ids = self.schema_collection.get()["ids"]
            if all_ids:
                self.schema_collection.delete(ids=all_ids)
            logger.info(f"Cleared {existing} existing schema docs")

        ids = []
        contents = []
        metadatas = []

        for doc in documents:
            doc_id = f"schema_{doc['table_name']}"
            ids.append(doc_id)
            contents.append(doc["content"])
            metadatas.append(doc["metadata"])

        self.schema_collection.add(
            ids=ids,
            documents=contents,
            metadatas=metadatas,
        )

        logger.info(f"Indexed {len(ids)} schema documents")
        return len(ids)

    def index_business_rules(self, documents: list[dict]) -> int:
        """
        index business rule documents into the business_rules collection.

        each doc should have: name, content, metadata
        clears existing docs first (full re-index).
        """
        existing = self.rules_collection.count()
        if existing > 0:
            all_ids = self.rules_collection.get()["ids"]
            if all_ids:
                self.rules_collection.delete(ids=all_ids)
            logger.info(f"Cleared {existing} existing business rule docs")

        ids = []
        contents = []
        metadatas = []

        for doc in documents:
            doc_id = f"rule_{doc['name']}"
            ids.append(doc_id)
            contents.append(doc["content"])
            metadatas.append(doc["metadata"])

        self.rules_collection.add(
            ids=ids,
            documents=contents,
            metadatas=metadatas,
        )

        logger.info(f"Indexed {len(ids)} business rule documents")
        return len(ids)

    def query_schema(self, question: str, top_k: int = 5) -> list[dict]:
        """retrieve the most relevant schema chunks for a question."""
        results = self.schema_collection.query(
            query_texts=[question],
            n_results=min(top_k, self.schema_collection.count()),
        )
        return self._format_results(results)

    def query_rules(self, question: str, top_k: int = 3) -> list[dict]:
        """retrieve the most relevant business rules for a question."""
        count = self.rules_collection.count()
        if count == 0:
            return []

        results = self.rules_collection.query(
            query_texts=[question],
            n_results=min(top_k, count),
        )
        return self._format_results(results)

    def _format_results(self, raw_results: dict) -> list[dict]:
        """convert ChromaDB's nested list format into flat dicts."""
        formatted = []
        if not raw_results["documents"] or not raw_results["documents"][0]:
            return formatted

        for i, doc in enumerate(raw_results["documents"][0]):
            entry = {
                "content": doc,
                "metadata": raw_results["metadatas"][0][i] if raw_results["metadatas"] else {},
                "distance": raw_results["distances"][0][i] if raw_results["distances"] else None,
            }
            formatted.append(entry)

        return formatted
