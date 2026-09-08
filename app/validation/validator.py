"""
SQL validation — SQLGlot-based syntax check, dialect validation, and security blocklist.

catches errors BEFORE hitting the database:
  - syntax errors (missing parens, bad keywords)
  - dialect mismatches
  - dangerous mutation queries (DROP, DELETE, INSERT, UPDATE, etc.)
"""

import logging
import sqlglot
from sqlglot import errors as sqlglot_errors

logger = logging.getLogger(__name__)

# queries containing any of these are blocked immediately
# lowercase for case-insensitive matching
BLOCKED_KEYWORDS = {
    "drop", "delete", "insert", "update", "alter", "create",
    "truncate", "replace", "merge", "grant", "revoke",
    "exec", "execute", "call",
}

# sqlglot node types that indicate mutations — belt and suspenders
BLOCKED_AST_TYPES = {
    sqlglot.exp.Drop,
    sqlglot.exp.Delete,
    sqlglot.exp.Insert,
    sqlglot.exp.Update,
    sqlglot.exp.Create,
    sqlglot.exp.Alter,
}


class ValidationResult:
    """result of validating a SQL query."""

    def __init__(self, is_valid: bool, error_type: str = "", error_message: str = "", is_recoverable: bool = True):
        self.is_valid = is_valid
        self.error_type = error_type
        self.error_message = error_message
        self.is_recoverable = is_recoverable  # can the LLM fix this?

    def __repr__(self):
        if self.is_valid:
            return "ValidationResult(valid)"
        return f"ValidationResult(invalid: {self.error_type} — {self.error_message})"


def validate_sql(sql: str, dialect: str = "sqlite") -> ValidationResult:
    """
    validate a SQL query through all checks.

    order matters:
    1. security blocklist first (cheapest, most important)
    2. syntax validation via SQLGlot parse
    3. AST-level mutation check (defense in depth)

    returns a ValidationResult with error details if invalid.
    """
    # strip semicolons and whitespace — sqlglot handles them weirdly sometimes
    sql = sql.strip().rstrip(";").strip()

    if not sql:
        return ValidationResult(
            is_valid=False,
            error_type="empty",
            error_message="Generated SQL is empty",
            is_recoverable=True,
        )

    # 1. keyword blocklist — fast rejection of obvious mutations
    security_result = _check_security_blocklist(sql)
    if not security_result.is_valid:
        return security_result

    # 2. parse with sqlglot for syntax validation
    parse_result = _check_syntax(sql, dialect)
    if not parse_result.is_valid:
        return parse_result

    # 3. AST-level mutation check — catches things the keyword check might miss
    ast_result = _check_ast_mutations(sql, dialect)
    if not ast_result.is_valid:
        return ast_result

    return ValidationResult(is_valid=True)


def _check_security_blocklist(sql: str) -> ValidationResult:
    """fast keyword-level check for dangerous operations."""
    # tokenize by splitting on whitespace and common delimiters
    # this isn't perfect but catches the obvious cases
    sql_lower = sql.lower()

    for keyword in BLOCKED_KEYWORDS:
        # check as a whole word — avoid matching "updated_at" as "update"
        # look for the keyword preceded by start-of-string or whitespace/paren
        import re
        pattern = r'(?:^|[\s(])' + re.escape(keyword) + r'(?:[\s(;]|$)'
        if re.search(pattern, sql_lower):
            return ValidationResult(
                is_valid=False,
                error_type="security",
                error_message=f"Query contains blocked keyword: {keyword.upper()}. Only SELECT queries are allowed.",
                is_recoverable=False,  # don't retry — this is policy, not a fixable error
            )

    return ValidationResult(is_valid=True)


def _check_syntax(sql: str, dialect: str) -> ValidationResult:
    """parse SQL with sqlglot to catch syntax errors."""
    try:
        # map our dialect names to sqlglot's
        sqlglot_dialect = _map_dialect(dialect)
        parsed = sqlglot.parse(sql, dialect=sqlglot_dialect)

        if not parsed or not parsed[0]:
            return ValidationResult(
                is_valid=False,
                error_type="syntax",
                error_message="SQLGlot returned empty parse result",
                is_recoverable=True,
            )

        return ValidationResult(is_valid=True)

    except sqlglot_errors.ParseError as e:
        return ValidationResult(
            is_valid=False,
            error_type="syntax",
            error_message=f"SQL syntax error: {str(e)}",
            is_recoverable=True,  # LLM can try to fix syntax errors
        )


def _check_ast_mutations(sql: str, dialect: str) -> ValidationResult:
    """walk the AST looking for mutation operations."""
    try:
        sqlglot_dialect = _map_dialect(dialect)
        parsed = sqlglot.parse(sql, dialect=sqlglot_dialect)

        for statement in parsed:
            if statement is None:
                continue
            for node in statement.walk():
                if type(node) in BLOCKED_AST_TYPES:
                    return ValidationResult(
                        is_valid=False,
                        error_type="security",
                        error_message=f"Query contains mutation operation: {type(node).__name__}. Only SELECT queries are allowed.",
                        is_recoverable=False,
                    )

        return ValidationResult(is_valid=True)

    except Exception:
        # if AST walk fails, we already passed syntax check — let it through
        return ValidationResult(is_valid=True)


def _map_dialect(dialect: str) -> str:
    """map our dialect names to sqlglot's dialect names."""
    mapping = {
        "sqlite": "sqlite",
        "postgres": "postgres",
        "postgresql": "postgres",
        "mysql": "mysql",
    }
    return mapping.get(dialect.lower(), dialect.lower())
