"""
FastAPI routes for the SQLPilot pipeline.

POST /query and POST /clarify together mirror the CLI's clarification loop
(app/cli.py::run), just split across two HTTP calls since the pipeline can't
block on stdin here. session_store bridges the gap in between.
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException

from app.agents.graph import pipeline
from app.agents.nodes.handle_clarification import handle_clarification
from app.api.session_store import session_store
from app.models.schemas import (
    ClarifyRequest,
    QueryRequest,
    QueryResponse,
    SchemaResponse,
    TableSchema,
)
from app.observability.tracing import deactivate_trace, finalize_trace, new_trace, use_trace

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/query", response_model=QueryResponse, summary="Ask a question")
def query(request: QueryRequest) -> QueryResponse:
    """
    Submit a natural language question. Returns SQL + results + explanation,
    or `status: "clarification_needed"` if the question is ambiguous -- in
    that case, call POST /clarify with the same session_id and your answer.
    """
    session_id = request.session_id or str(uuid.uuid4())

    state = {
        "user_question": request.question,
        "session_id": session_id,
        "sql_dialect": "sqlite",
    }

    trace = new_trace("sqlpilot.query", session_id=session_id, input=request.question)
    token = use_trace(trace)
    try:
        result = _run_pipeline(state)
    finally:
        deactivate_trace(token)

    if result.get("final_status") == "clarification_needed" and result.get("is_ambiguous"):
        # pause here -- hold the trace and state until /clarify continues it
        session_store.save(session_id, result, trace=trace)
        return _clarification_response(result, session_id)

    finalize_trace(trace, output=_trace_output(result), metadata=_trace_metadata(result))
    return _final_response(result, session_id)


@router.post("/clarify", response_model=QueryResponse, summary="Answer a clarification question")
def clarify(request: ClarifyRequest) -> QueryResponse:
    """
    Answer the clarification question from a prior POST /query call. May
    itself return another `clarification_needed` (up to 2 rounds total).
    """
    pending = session_store.pop(request.session_id)
    if pending is None:
        raise HTTPException(
            status_code=404,
            detail="No pending clarification for this session_id. Call /query first.",
        )

    enriched_state = dict(pending.state)
    enriched_state["clarification_response"] = request.response
    updates = handle_clarification(enriched_state)
    state = {**enriched_state, **updates}
    state["final_status"] = ""

    token = use_trace(pending.trace)
    try:
        result = _run_pipeline(state)
    finally:
        deactivate_trace(token)

    if result.get("final_status") == "clarification_needed" and result.get("is_ambiguous"):
        session_store.save(request.session_id, result, trace=pending.trace)
        return _clarification_response(result, request.session_id)

    finalize_trace(pending.trace, output=_trace_output(result), metadata=_trace_metadata(result))
    return _final_response(result, request.session_id)


@router.get("/schema", response_model=SchemaResponse, summary="View the indexed database schema")
def schema() -> SchemaResponse:
    """Return the introspected schema (tables, columns, row counts) used to ground SQL generation."""
    from app.rag.schema_introspector import introspect_sqlite

    try:
        docs = introspect_sqlite()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Schema introspection failed: {e}") from e

    tables = [
        TableSchema(
            table_name=doc["table_name"],
            content=doc["content"],
            column_count=doc["metadata"]["column_count"],
            row_count=doc["metadata"]["row_count"],
        )
        for doc in docs
    ]
    return SchemaResponse(tables=tables)


def _run_pipeline(state: dict) -> dict:
    """invoke the graph, translating unexpected exceptions into a 500."""
    try:
        return pipeline.invoke(state)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        logger.exception("Pipeline invocation failed")
        raise HTTPException(status_code=500, detail=f"Internal error: {e}") from e


def _clarification_response(result: dict, session_id: str) -> QueryResponse:
    return QueryResponse(
        status="clarification_needed",
        session_id=session_id,
        clarification_question=result.get("clarification_question", ""),
        clarification_options=result.get("clarification_options", []),
        clarification_round=result.get("clarification_round", 0) + 1,
    )


def _final_response(result: dict, session_id: str) -> QueryResponse:
    status = result.get("final_status", "error")
    if status == "success":
        return QueryResponse(
            status="success",
            session_id=session_id,
            sql=result.get("generated_sql", ""),
            assumptions=result.get("llm_assumptions", ""),
            columns=result.get("query_columns", []),
            rows=result.get("query_results", []),
            explanation=result.get("explanation", ""),
        )
    return QueryResponse(
        status="error",
        session_id=session_id,
        sql=result.get("generated_sql") or None,
        error=result.get("explanation") or result.get("execution_error") or result.get("validation_error") or "Unknown error",
    )


def _trace_output(result: dict) -> dict:
    return {
        "final_status": result.get("final_status"),
        "generated_sql": result.get("generated_sql"),
        "explanation": result.get("explanation"),
    }


def _trace_metadata(result: dict) -> dict:
    """quality metrics per IMPLEMENTATION_PLAN.md Phase 7 -- how often did we
    need to self-correct or ask for clarification?"""
    return {
        "clarification_rounds": result.get("clarification_round", 0),
        "validation_retry_count": result.get("validation_retry_count", 0),
        "execution_retry_count": result.get("execution_retry_count", 0),
        "self_correction_attempts": len(result.get("correction_history", [])),
    }
