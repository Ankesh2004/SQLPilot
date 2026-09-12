"""
API contract tests -- the endpoints and error codes that don't need an LLM.

/query and /clarify happy paths need a live LLM provider, so they're covered by
the eval harness (tests/eval/) rather than here. What's pinned down here is the
routing and validation surface: status codes, response shapes, and the schema
endpoint.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)

needs_demo_db = pytest.mark.skipif(
    not Path(settings.sqlite_db_path).exists(),
    reason="demo database not seeded -- run scripts/seed_database.py",
)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_docs_are_served():
    assert client.get("/openapi.json").status_code == 200


def test_empty_question_is_rejected():
    response = client.post("/query", json={"question": ""})
    assert response.status_code == 422


def test_missing_question_is_rejected():
    assert client.post("/query", json={}).status_code == 422


def test_clarify_without_a_pending_session_is_404():
    response = client.post("/clarify", json={"session_id": "no-such-session", "response": "MRR"})
    assert response.status_code == 404
    assert "clarification" in response.json()["detail"].lower()


def test_clarify_with_empty_response_is_rejected():
    response = client.post("/clarify", json={"session_id": "abc", "response": ""})
    assert response.status_code == 422


@needs_demo_db
def test_schema_lists_the_demo_tables():
    response = client.get("/schema")
    assert response.status_code == 200
    tables = response.json()["tables"]
    assert {t["table_name"] for t in tables} >= {"customers", "subscriptions", "invoices"}
    for table in tables:
        assert table["column_count"] > 0
        assert table["content"]
