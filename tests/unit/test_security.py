"""
Sandbox tests -- rate limiter, read-only enforcement, statement timeout, row cap.

These cover the Phase 6 guarantees at the layer that actually enforces them
(the SQLite connection), not just the blocklist above it. No API keys needed.
"""

import sqlite3

import pytest

from app.config import settings
from app.db.connection import SQLiteConnector
from app.security.rate_limiter import RateLimiter

# --- rate limiter ---


def test_allows_up_to_the_limit_then_blocks():
    limiter = RateLimiter(max_per_minute=3)
    assert [limiter.check("s1") for _ in range(3)] == [True, True, True]
    assert limiter.check("s1") is False


def test_sessions_are_isolated():
    limiter = RateLimiter(max_per_minute=1)
    assert limiter.check("s1") is True
    assert limiter.check("s1") is False
    # a different session still has its full budget
    assert limiter.check("s2") is True


def test_reset_clears_a_session():
    limiter = RateLimiter(max_per_minute=1)
    limiter.check("s1")
    assert limiter.check("s1") is False
    limiter.reset("s1")
    assert limiter.check("s1") is True


# --- database sandbox ---


@pytest.fixture
def demo_db(tmp_path):
    """a throwaway two-row database, so these tests never touch data/demo.db."""
    path = tmp_path / "test.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT);
        INSERT INTO widgets (id, name) VALUES (1, 'alpha'), (2, 'beta'), (3, 'gamma');
        """
    )
    conn.commit()
    conn.close()
    return str(path)


def test_select_returns_columns_and_rows(demo_db):
    result = SQLiteConnector(demo_db).execute_query("SELECT id, name FROM widgets ORDER BY id")
    assert result["columns"] == ["id", "name"]
    assert result["row_count"] == 3
    assert result["rows"][0] == {"id": 1, "name": "alpha"}


def test_empty_result_set_is_handled(demo_db):
    result = SQLiteConnector(demo_db).execute_query("SELECT * FROM widgets WHERE id = 999")
    assert result == {"columns": [], "rows": [], "row_count": 0}


def test_writes_are_blocked_at_the_connection_level(demo_db):
    # this bypasses the validator entirely -- PRAGMA query_only is the last line of defense
    with pytest.raises(RuntimeError, match="read-only"):
        SQLiteConnector(demo_db).execute_query("INSERT INTO widgets (name) VALUES ('delta')")


def test_row_cap_is_enforced(demo_db, monkeypatch):
    monkeypatch.setattr(settings, "max_result_rows", 2)
    result = SQLiteConnector(demo_db).execute_query("SELECT * FROM widgets")
    assert result["row_count"] == 2


def test_runaway_query_times_out(demo_db, monkeypatch):
    monkeypatch.setattr(settings, "statement_timeout_ms", 250)
    endless = (
        "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT count(*) FROM c"
    )
    with pytest.raises(RuntimeError, match="timed out"):
        SQLiteConnector(demo_db).execute_query(endless)


def test_missing_database_fails_with_a_useful_message(tmp_path):
    with pytest.raises(FileNotFoundError, match="seed_database"):
        SQLiteConnector(str(tmp_path / "nope.db"))
