"""
handle_clarification node — processes the user's response to a clarification question.

when the pipeline pauses for clarification, the user responds, and this node:
1. records the Q&A in clarification_history
2. builds an enriched question combining the original + clarification
3. resets ambiguity flags so the pipeline can re-evaluate
"""

import logging
from app.agents.state import AgentState
from app.agents.prompts_clarification import ENRICHED_QUESTION_TEMPLATE

logger = logging.getLogger(__name__)


def handle_clarification(state: AgentState) -> dict:
    """
    process a user's clarification response and enrich the question.

    reads: user_question, clarification_question, clarification_response,
           clarification_history, clarification_round
    writes: clarified_question, clarification_history, clarification_round,
            is_ambiguous (reset)
    """
    original_question = state["user_question"]
    clarification_q = state.get("clarification_question", "")
    user_response = state.get("clarification_response", "")
    history = state.get("clarification_history", [])
    current_round = state.get("clarification_round", 0)

    # record this round in history
    history = list(history)  # copy to avoid mutation
    history.append({
        "question": clarification_q,
        "answer": user_response,
        "round": current_round + 1,
    })

    # build enriched question that incorporates the clarification
    enriched = ENRICHED_QUESTION_TEMPLATE.format(
        original_question=original_question,
        clarification_question=clarification_q,
        user_response=user_response,
    )

    logger.info(
        f"Clarification round {current_round + 1}: "
        f"Q: {clarification_q} -> A: {user_response}"
    )

    return {
        "clarified_question": enriched,
        "clarification_history": history,
        "clarification_round": current_round + 1,
        # reset ambiguity so the next check_ambiguity run re-evaluates
        "is_ambiguous": False,
        "clarification_question": "",
        "clarification_options": [],
    }
