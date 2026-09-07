"""
LangGraph graph definition.

Phase 1: linear pipeline (generate → execute → explain).
Phase 4+: adds cycles for validation and self-correction loops.
"""

from langgraph.graph import StateGraph, END

from app.agents.state import AgentState
from app.agents.nodes.generate_sql import generate_sql
from app.agents.nodes.execute_query import execute_query
from app.agents.nodes.explain_results import explain_results


def build_graph() -> StateGraph:
    """
    construct the LangGraph state machine.

    Phase 1 is a simple linear chain:
        generate_sql → execute_query → explain_results → END

    no cycles, no validation, no clarification.
    just the happy path to prove the pipeline works end-to-end.
    """
    graph = StateGraph(AgentState)

    # add nodes
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("execute_query", execute_query)
    graph.add_node("explain_results", explain_results)

    # wire them up: linear flow
    graph.set_entry_point("generate_sql")
    graph.add_edge("generate_sql", "execute_query")
    graph.add_edge("execute_query", "explain_results")
    graph.add_edge("explain_results", END)

    return graph.compile()


# the compiled graph — import this to run queries
pipeline = build_graph()
