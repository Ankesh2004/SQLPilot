"""
LangGraph graph definition.

Phase 4 adds validation and self-correction loops:
  retrieve → ambiguity check → generate → validate → [fix loop] → execute → [fix loop] → explain

Two independent correction loops per DESIGN.md §7.4:
  - Loop 1 (syntax): validate_sql fails → correct_sql → re-validate (max 2 retries)
  - Loop 2 (runtime): execute_query fails → correct_sql → re-validate → re-execute (max 2 retries)
"""

from langgraph.graph import StateGraph, END

from app.agents.state import AgentState
from app.agents.nodes.retrieve_context import retrieve_context
from app.agents.nodes.check_ambiguity import check_ambiguity
from app.agents.nodes.generate_sql import generate_sql
from app.agents.nodes.validate_sql import validate_sql_node
from app.agents.nodes.correct_sql import correct_sql
from app.agents.nodes.execute_query import execute_query
from app.agents.nodes.explain_results import explain_results


# --- routing functions ---

def _route_after_ambiguity(state: AgentState) -> str:
    """decide what to do after ambiguity check."""
    is_ambiguous = state.get("is_ambiguous", False)
    clarification_round = state.get("clarification_round", 0)

    if not is_ambiguous:
        return "generate_sql"
    if clarification_round >= 2:
        return "generate_sql"
    return "stop_for_clarification"


def _route_after_validation(state: AgentState) -> str:
    """decide what to do after SQL validation."""
    passed = state.get("validation_passed", False)

    if passed:
        return "execute_query"

    error_type = state.get("validation_error_type", "")

    # security violations are unrecoverable — go straight to explain (with error)
    if error_type == "security":
        return "explain_with_error"

    # syntax errors are recoverable — check retry budget
    retry_count = state.get("validation_retry_count", 0)
    if retry_count >= 2:
        # exhausted validation retries — report the error
        return "explain_with_error"

    # still have budget — try to fix it
    return "correct_sql"


def _route_after_execution(state: AgentState) -> str:
    """decide what to do after query execution."""
    error = state.get("execution_error", "")

    if not error:
        return "explain_results"

    # check if the error is recoverable
    history = state.get("correction_history", [])
    last_error = history[-1] if history else {}
    is_recoverable = last_error.get("recoverable", True)

    if not is_recoverable:
        return "explain_with_error"

    # check retry budget
    retry_count = state.get("execution_retry_count", 0)
    if retry_count >= 2:
        return "explain_with_error"

    return "correct_sql"


def _route_after_correction(state: AgentState) -> str:
    """after correction, always re-validate (never go directly to execution)."""
    # per DESIGN.md §7.4.1: corrections always re-routed through validation
    return "validate_sql"


def _stop_for_clarification(state: AgentState) -> dict:
    """signal that we need user input and stop the graph."""
    return {"final_status": "clarification_needed"}


def _explain_with_error(state: AgentState) -> dict:
    """
    terminal node for unrecoverable errors.

    instead of crashing, we report what went wrong in a user-friendly way.
    """
    validation_error = state.get("validation_error", "")
    execution_error = state.get("execution_error", "")
    error = validation_error or execution_error or "Unknown error"

    return {
        "explanation": f"I wasn't able to generate a valid query for this question. Error: {error}",
        "final_status": "error",
    }


def build_graph() -> StateGraph:
    """
    construct the LangGraph state machine with validation + correction loops.

    flow:
        retrieve_context → check_ambiguity
            → [ambiguous] → stop_for_clarification → END
            → [clear] → generate_sql → validate_sql
                → [valid] → execute_query
                    → [success] → explain_results → END
                    → [recoverable error] → correct_sql → validate_sql (loop)
                    → [unrecoverable] → explain_with_error → END
                → [syntax error] → correct_sql → validate_sql (loop)
                → [security] → explain_with_error → END
    """
    graph = StateGraph(AgentState)

    # add all nodes
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("check_ambiguity", check_ambiguity)
    graph.add_node("stop_for_clarification", _stop_for_clarification)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("validate_sql", validate_sql_node)
    graph.add_node("correct_sql", correct_sql)
    graph.add_node("execute_query", execute_query)
    graph.add_node("explain_results", explain_results)
    graph.add_node("explain_with_error", _explain_with_error)

    # entry
    graph.set_entry_point("retrieve_context")

    # retrieve → ambiguity check
    graph.add_edge("retrieve_context", "check_ambiguity")

    # ambiguity routing
    graph.add_conditional_edges(
        "check_ambiguity",
        _route_after_ambiguity,
        {
            "generate_sql": "generate_sql",
            "stop_for_clarification": "stop_for_clarification",
        },
    )
    graph.add_edge("stop_for_clarification", END)

    # generate → validate
    graph.add_edge("generate_sql", "validate_sql")

    # validation routing (Loop 1: syntax fix)
    graph.add_conditional_edges(
        "validate_sql",
        _route_after_validation,
        {
            "execute_query": "execute_query",
            "correct_sql": "correct_sql",
            "explain_with_error": "explain_with_error",
        },
    )

    # correction → always re-validate (never skip to execution)
    graph.add_conditional_edges(
        "correct_sql",
        _route_after_correction,
        {"validate_sql": "validate_sql"},
    )

    # execution routing (Loop 2: runtime fix)
    graph.add_conditional_edges(
        "execute_query",
        _route_after_execution,
        {
            "explain_results": "explain_results",
            "correct_sql": "correct_sql",
            "explain_with_error": "explain_with_error",
        },
    )

    # terminal nodes
    graph.add_edge("explain_results", END)
    graph.add_edge("explain_with_error", END)

    return graph.compile()


# the compiled graph
pipeline = build_graph()
