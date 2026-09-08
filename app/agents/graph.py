"""
LangGraph graph definition.

Phase 3 adds the clarification loop:
  retrieve → check_ambiguity → [clear? → generate] [ambiguous? → END with clarification_needed]

The clarification loop is managed by the CALLER (CLI/Streamlit), not inside the graph.
When the graph returns with final_status == "clarification_needed", the caller:
  1. Shows the clarification question + options to the user
  2. Gets the user's response
  3. Feeds it back through handle_clarification
  4. Re-invokes the graph with the enriched state

Why not use LangGraph interrupt()? Two reasons:
  - It requires a checkpointer (adds infra complexity for MVP)
  - The caller-managed loop is simpler and works the same way for CLI and Streamlit
"""

from langgraph.graph import StateGraph, END

from app.agents.state import AgentState
from app.agents.nodes.retrieve_context import retrieve_context
from app.agents.nodes.check_ambiguity import check_ambiguity
from app.agents.nodes.generate_sql import generate_sql
from app.agents.nodes.execute_query import execute_query
from app.agents.nodes.explain_results import explain_results


def _route_after_ambiguity(state: AgentState) -> str:
    """decide what to do after ambiguity check."""
    is_ambiguous = state.get("is_ambiguous", False)
    clarification_round = state.get("clarification_round", 0)

    if not is_ambiguous:
        return "generate_sql"

    if clarification_round >= 2:
        # exhausted budget — proceed with best guess
        return "generate_sql"

    # ambiguous — stop the graph so the caller can get user input
    return "stop_for_clarification"


def _route_after_execution(state: AgentState) -> str:
    """decide what to do after query execution."""
    # Phase 4 will add retry logic here
    return "explain_results"


def _stop_for_clarification(state: AgentState) -> dict:
    """signal that we need user input and stop the graph."""
    return {
        "final_status": "clarification_needed",
    }


def build_graph() -> StateGraph:
    """
    construct the LangGraph state machine.

    flow:
        retrieve_context → check_ambiguity
            → [clear] → generate_sql → execute_query → explain_results → END
            → [ambiguous] → stop_for_clarification → END (caller handles it)
    """
    graph = StateGraph(AgentState)

    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("check_ambiguity", check_ambiguity)
    graph.add_node("stop_for_clarification", _stop_for_clarification)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("execute_query", execute_query)
    graph.add_node("explain_results", explain_results)

    graph.set_entry_point("retrieve_context")
    graph.add_edge("retrieve_context", "check_ambiguity")

    graph.add_conditional_edges(
        "check_ambiguity",
        _route_after_ambiguity,
        {
            "generate_sql": "generate_sql",
            "stop_for_clarification": "stop_for_clarification",
        },
    )

    # clarification stops the graph — caller re-invokes
    graph.add_edge("stop_for_clarification", END)

    # generation → execution → explanation
    graph.add_edge("generate_sql", "execute_query")
    graph.add_conditional_edges(
        "execute_query",
        _route_after_execution,
        {"explain_results": "explain_results"},
    )
    graph.add_edge("explain_results", END)

    return graph.compile()


# the compiled graph — import this to run queries
pipeline = build_graph()
