"""
Streamlit chat frontend for SQLPilot.

Run with:
    streamlit run streamlit_app.py

Built out in Phase 8. This is the placeholder.
"""

# TODO (Phase 8): implement full chat UI
# - st.chat_message / st.chat_input for conversation
# - handle clarification dialogue (show options as buttons)
# - display SQL, results table, and explanation
# - session state for multi-turn conversations

import streamlit as st

st.set_page_config(page_title="SQLPilot", page_icon="🛩️", layout="wide")
st.title("🛩️ SQLPilot")
st.caption("Text-to-SQL with clarification — asks before it guesses")
st.info("🚧 Frontend under construction. Coming in Phase 8.")
