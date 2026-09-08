"""
Streamlit chat frontend for SQLPilot.

Run with:
    streamlit run streamlit_app.py

Talks to the FastAPI backend (app/main.py) over HTTP -- start it first:
    uvicorn app.main:app --reload

Override the backend URL with the SQLPILOT_API_URL env var if it's not
running on localhost:8000.
"""

import os
import uuid

import httpx
import streamlit as st

API_BASE_URL = os.getenv("SQLPILOT_API_URL", "http://localhost:8000")
REQUEST_TIMEOUT = 120.0  # LLM retries with backoff can take a while

st.set_page_config(page_title="SQLPilot", page_icon="🛩️", layout="wide")
st.title("🛩️ SQLPilot")
st.caption("Text-to-SQL with clarification — asks before it guesses")

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []  # [{"role": "user"|"assistant", "content"?: str, "result"?: dict}]
if "pending_clarification" not in st.session_state:
    st.session_state.pending_clarification = None  # QueryResponse dict when awaiting an answer

with st.sidebar:
    st.subheader("Session")
    st.caption(f"`{st.session_state.session_id}`")
    if st.button("New conversation"):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.pending_clarification = None
        st.rerun()


def _call_api(path: str, payload: dict) -> dict:
    """POST to the backend, translating connection/HTTP errors into an error result."""
    try:
        resp = httpx.post(f"{API_BASE_URL}{path}", json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json().get("detail", str(e))
        except ValueError:
            detail = str(e)
        return {"status": "error", "error": detail}
    except httpx.RequestError as e:
        return {"status": "error", "error": f"Could not reach SQLPilot API at {API_BASE_URL}: {e}"}


def _render_result(result: dict) -> None:
    """render one assistant turn's SQL / results table / explanation / error."""
    if result.get("sql"):
        st.code(result["sql"], language="sql")
    if result.get("assumptions"):
        st.caption(f"Assumptions: {result['assumptions']}")
    rows = result.get("rows")
    if rows is not None:
        if rows:
            st.dataframe(rows, use_container_width=True)
        else:
            st.caption("(no rows returned)")
    if result.get("explanation"):
        st.write(result["explanation"])
    if result.get("error"):
        st.error(result["error"])


def _handle_result(result: dict) -> None:
    """either queue the clarification UI, or record the final answer as a chat turn."""
    if result.get("status") == "clarification_needed":
        st.session_state.pending_clarification = result
    else:
        st.session_state.pending_clarification = None
        st.session_state.messages.append({"role": "assistant", "result": result})


# replay conversation history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if "content" in msg:
            st.write(msg["content"])
        if "result" in msg:
            _render_result(msg["result"])

pending = st.session_state.pending_clarification

if pending:
    with st.chat_message("assistant"):
        st.write(pending.get("clarification_question", ""))
        options = pending.get("clarification_options") or []
        if options:
            cols = st.columns(len(options))
            for col, option in zip(cols, options):
                if col.button(option, key=f"clarify_opt_{option}"):
                    st.session_state.messages.append({"role": "user", "content": option})
                    with st.spinner("Thinking..."):
                        result = _call_api(
                            "/clarify",
                            {"session_id": st.session_state.session_id, "response": option},
                        )
                    _handle_result(result)
                    st.rerun()

    free_text = st.chat_input("Or type your own answer...")
    if free_text:
        st.session_state.messages.append({"role": "user", "content": free_text})
        with st.spinner("Thinking..."):
            result = _call_api(
                "/clarify",
                {"session_id": st.session_state.session_id, "response": free_text},
            )
        _handle_result(result)
        st.rerun()
else:
    question = st.chat_input("Ask a question about your data...")
    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.spinner("Thinking..."):
            result = _call_api(
                "/query",
                {"session_id": st.session_state.session_id, "question": question},
            )
        _handle_result(result)
        st.rerun()
