"""
LangGraph graph definition.

Phase 1: linear pipeline (generate → execute → explain).
Phase 2: added RAG retrieval node before generation.
Phase 4+: adds cycles for validation and self-correction loops.
"""

from langgraph.graph import StateGraph, END

from app.agents.state import AgentState
from app.agents.nodes.retrieve_context import retrieve_context
from app.agents.nodes.generate_sql import generate_sql
from app.agents.nodes.execute_query import execute_query
from app.agents.nodes.explain_results import explain_results


def build_graph() -> StateGraph:
    """
    construct the LangGraph state machine.

    Phase 2 adds RAG retrieval:
        retrieve_context → generate_sql → execute_query → explain_results → END

    still linear, no cycles. validation and correction come in Phase 4.
    """
    graph = StateGraph(AgentState)

    # add nodes
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("execute_query", execute_query)
    graph.add_node("explain_results", explain_results)

    # wire them up: retrieve → generate → execute → explain
    graph.set_entry_point("retrieve_context")
    graph.add_edge("retrieve_context", "generate_sql")
    graph.add_edge("generate_sql", "execute_query")
    graph.add_edge("execute_query", "explain_results")
    graph.add_edge("explain_results", END)

    return graph.compile()


# the compiled graph — import this to run queries
pipeline = build_graph()
