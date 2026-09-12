"""
Validator tests -- the three security layers and the syntax check.

These are the checks that stand between a hallucinated query and the database,
so they're worth pinning down. No API keys or database needed.
"""

import pytest

from app.validation.validator import validate_sql


def test_plain_select_is_valid():
    result = validate_sql("SELECT id, full_name FROM customers LIMIT 10")
    assert result.is_valid


def test_cte_and_join_are_valid():
    sql = """
    WITH active AS (
        SELECT customer_id FROM subscriptions WHERE status = 'active'
    )
    SELECT c.full_name FROM customers c JOIN active a ON a.customer_id = c.id
    """
    assert validate_sql(sql).is_valid


def test_trailing_semicolon_is_tolerated():
    assert validate_sql("SELECT 1;").is_valid


def test_empty_sql_is_recoverable():
    result = validate_sql("   ")
    assert not result.is_valid
    assert result.error_type == "empty"
    assert result.is_recoverable


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE customers",
        "DELETE FROM customers WHERE id = 1",
        "INSERT INTO customers (full_name) VALUES ('x')",
        "UPDATE customers SET full_name = 'x'",
        "ALTER TABLE customers ADD COLUMN x TEXT",
        "TRUNCATE TABLE customers",
        "GRANT ALL ON customers TO public",
    ],
)
def test_mutations_are_blocked_and_not_retried(sql):
    result = validate_sql(sql)
    assert not result.is_valid
    assert result.error_type == "security"
    # policy violations must not burn self-correction retries
    assert not result.is_recoverable


def test_mutation_hidden_in_subquery_is_blocked():
    sql = "SELECT * FROM customers WHERE id IN (SELECT id FROM (DELETE FROM subscriptions))"
    result = validate_sql(sql)
    assert not result.is_valid
    assert result.error_type == "security"


def test_column_named_like_a_keyword_is_not_a_false_positive():
    # "updated_at" must not trip the UPDATE blocklist -- whole-word matching
    result = validate_sql("SELECT id, updated_at, created_at FROM customers")
    assert result.is_valid


def test_syntax_error_is_recoverable():
    result = validate_sql("SELECT FROM WHERE customers")
    assert not result.is_valid
    assert result.error_type == "syntax"
    # the LLM gets a shot at fixing syntax
    assert result.is_recoverable


def test_dialect_is_respected():
    # postgres-only cast syntax parses under postgres
    assert validate_sql("SELECT '1'::int AS n", dialect="postgres").is_valid
