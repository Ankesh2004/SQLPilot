"""
In-memory store bridging the two-request clarification flow.

POST /query may return status="clarification_needed"; the pending pipeline
state (and the active Langfuse trace, if tracing is enabled) is held here
until the client calls POST /clarify with the same session_id.

In-memory only, same tradeoff as the rate limiter (app/security/rate_limiter.py)
-- fine for a single-process demo deployment, not for multi-worker production.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class PendingSession:
    state: dict[str, Any]
    trace: Any = None  # Langfuse StatefulTraceClient, or None if tracing is disabled


class SessionStore:
    """holds at most one pending clarification per session_id."""

    def __init__(self):
        self._sessions: dict[str, PendingSession] = {}

    def save(self, session_id: str, state: dict, trace=None) -> None:
        self._sessions[session_id] = PendingSession(state=state, trace=trace)

    def pop(self, session_id: str) -> PendingSession | None:
        """retrieve and remove the pending session, if any."""
        return self._sessions.pop(session_id, None)


# shared instance
session_store = SessionStore()
