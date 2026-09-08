"""
Langfuse tracing for the SQLPilot pipeline.

One trace per user question (spanning all clarification rounds). Every
LangGraph node runs inside a nested span (see `traced_node`), and every LLM
call inside a node logs a nested generation with token usage (see
`log_generation`), so a full request is visible end-to-end in the Langfuse
dashboard: retrieval -> ambiguity check -> generation -> validation ->
correction attempts -> execution -> explanation.

No-ops everywhere if LANGFUSE_PUBLIC_KEY/SECRET_KEY aren't set, so local dev
without a Langfuse account behaves exactly as before.
"""

import contextvars
import functools
import logging

from app.config import settings

logger = logging.getLogger(__name__)

_enabled = bool(settings.langfuse_public_key and settings.langfuse_secret_key)
_client = None

# tracks the active trace/span for the current call stack so nodes and LLM
# clients can attach to the right parent without passing objects around
_current_trace = contextvars.ContextVar("langfuse_trace", default=None)
_current_span = contextvars.ContextVar("langfuse_span", default=None)


def is_enabled() -> bool:
    return _enabled


def get_client():
    """lazily create the Langfuse client singleton. returns None if not configured."""
    global _client
    if not _enabled:
        return None
    if _client is None:
        from langfuse import Langfuse
        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    return _client


def start_trace(name: str, session_id: str | None = None, input=None):
    """
    start a new trace for one user question. returns a contextvar token to
    pass to end_trace, or None if tracing is disabled.
    """
    trace = new_trace(name, session_id=session_id, input=input)
    return use_trace(trace)


def end_trace(token, output=None, metadata=None):
    """close out the trace and flush queued events to Langfuse."""
    if token is None:
        return
    trace = _current_trace.get()
    finalize_trace(trace, output=output, metadata=metadata)
    _current_trace.reset(token)


def new_trace(name: str, session_id: str | None = None, input=None):
    """
    create a trace object directly, without touching the active-trace
    contextvar. for callers that manage the trace across multiple separate
    calls themselves (e.g. the HTTP API's /query -> /clarify flow, where
    each request is its own call stack and can't share a contextvar token).
    returns None if tracing is disabled.
    """
    client = get_client()
    if client is None:
        return None
    return client.trace(name=name, session_id=session_id, input=input)


def use_trace(trace):
    """
    activate an existing trace object (from new_trace) for the current call
    stack, so traced_node/log_generation/score_trace attach to it. returns a
    contextvar token to pass to deactivate_trace, or None if trace is None.
    """
    if trace is None:
        return None
    return _current_trace.set(trace)


def deactivate_trace(token) -> None:
    """undo use_trace -- call in a `finally` after the traced work is done."""
    if token is not None:
        _current_trace.reset(token)


def finalize_trace(trace, output=None, metadata=None) -> None:
    """close out a trace object and flush queued events to Langfuse."""
    if trace is None:
        return
    trace.update(output=output, metadata=metadata)
    client = get_client()
    if client is not None:
        client.flush()


def traced_node(node_name: str):
    """
    decorator for LangGraph node functions -- wraps each call as a Langfuse
    span nested under the active trace. no-ops if tracing is disabled or no
    trace is active (e.g. tests that call a node function directly).
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(state):
            trace = _current_trace.get()
            if trace is None:
                return fn(state)

            span = trace.span(name=node_name, input=_safe_preview(state))
            token = _current_span.set(span)
            try:
                result = fn(state)
                span.end(output=_safe_preview(result))
                return result
            except Exception as e:
                span.end(level="ERROR", status_message=str(e))
                raise
            finally:
                _current_span.reset(token)
        return wrapper
    return decorator


def log_generation(name: str, model: str, input, output, usage: dict | None = None, metadata: dict | None = None):
    """
    log one LLM call as a generation, nested under the current node span
    (or directly under the trace if called outside a traced node). no-op if
    tracing is disabled or no trace is active.
    """
    parent = _current_span.get() or _current_trace.get()
    if parent is None:
        return
    parent.generation(name=name, model=model, input=input, output=output, usage=usage, metadata=metadata)


def score_trace(name: str, value, comment: str | None = None):
    """attach a score (e.g. user feedback) to the active trace."""
    trace = _current_trace.get()
    if trace is None:
        return
    trace.score(name=name, value=value, comment=comment)


def _safe_preview(state, max_len: int = 2000):
    """keep trace payloads small and serializable -- truncate long strings/lists."""
    if not isinstance(state, dict):
        return state
    preview = {}
    for k, v in state.items():
        if isinstance(v, str) and len(v) > max_len:
            preview[k] = v[:max_len] + f"...(truncated, {len(v)} chars total)"
        elif isinstance(v, list) and len(v) > 20:
            preview[k] = v[:20] + [f"...({len(v) - 20} more)"]
        else:
            preview[k] = v
    return preview
