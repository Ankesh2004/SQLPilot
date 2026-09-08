"""
AgentState — the typed dictionary that flows through every LangGraph node.

this is the single source of truth for what the pipeline knows at any point.
every node reads from it, does its thing, and writes back to it.
"""

from typing import TypedDict, Optional


class AgentState(TypedDict, total=False):
    """state that gets passed through the LangGraph pipeline."""

    # --- user input ---
    user_question: str                    # the original natural language question
    clarification_history: list[dict]     # previous clarification Q&A rounds
    clarified_question: str               # question after clarification enrichment

    # --- RAG context ---
    schema_context: str                   # retrieved schema chunks (joined text)
    business_rules_context: str           # retrieved business rules (joined text)

    # --- ambiguity detection ---
    is_ambiguous: bool                    # did the system detect ambiguity?
    ambiguity_type: str                   # what kind of ambiguity
    clarification_question: str           # the follow-up question to ask the user
    clarification_options: list[str]      # multiple-choice options (if any)
    clarification_response: str           # user's answer to the clarification question
    clarification_round: int             # which round of clarification we're on (max 2)

    # --- SQL generation ---
    generated_sql: str                    # the SQL query the LLM produced
    llm_assumptions: str                  # what assumptions the LLM made (for transparency)
    sql_dialect: str                      # "sqlite" or "postgres"

    # --- validation ---
    validation_passed: bool                # did the SQL pass all validation checks?
    validation_error: str                  # validation error message (if any)
    validation_error_type: str             # "syntax", "security", "empty"
    is_safe: bool                         # did it pass the security blocklist?
    safety_error: str                     # security violation message (if any)

    # --- self-correction (see DESIGN.md §7.4) ---
    validation_retry_count: int           # syntax fix attempts (max 2)
    execution_retry_count: int            # runtime fix attempts (max 2)
    correction_history: list[dict]        # append-only log of all failed attempts
    # each entry: {"attempt": int, "sql": str, "error_type": str,
    #              "error_message": str, "stage": str}

    # --- execution ---
    query_results: list[dict]             # rows returned from the database
    query_columns: list[str]              # column names from the result set
    execution_error: str                  # DB runtime error (if any)

    # --- output ---
    explanation: str                      # plain-English explanation of results
    final_status: str                     # "success", "clarification_needed", "error"
