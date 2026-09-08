"""
check_ambiguity node — asks the LLM if a question is clear enough to generate SQL.

this is the gatekeeper that decides:
  - clear question → proceed to generate_sql
  - ambiguous question → interrupt, ask user for clarification

sits between retrieve_context and generate_sql in the pipeline.
"""

import logging
from app.agents.state import AgentState
from app.agents.prompts_clarification import (
    AMBIGUITY_DETECTION_SYSTEM,
    AMBIGUITY_DETECTION_USER,
)
from app.llm import get_llm_client

logger = logging.getLogger(__name__)


def check_ambiguity(state: AgentState) -> dict:
    """
    analyze the user's question for ambiguity using the LLM.

    reads: user_question, schema_context, business_rules_context, clarification_history
    writes: is_ambiguous, ambiguity_type, clarification_question, clarification_options
    """
    question = state.get("clarified_question") or state["user_question"]
    schema = state.get("schema_context", "")
    rules = state.get("business_rules_context", "")
    history = state.get("clarification_history", [])

    # format clarification history for the prompt
    if history:
        history_text = "\n".join(
            f"  Q: {h['question']}\n  A: {h['answer']}" for h in history
        )
    else:
        history_text = "(No previous clarifications)"

    llm = get_llm_client()

    user_prompt = AMBIGUITY_DETECTION_USER.format(
        schema=schema,
        business_rules=rules,
        clarification_history=history_text,
        question=question,
    )

    result = llm.generate_structured(user_prompt, AMBIGUITY_DETECTION_SYSTEM)

    is_ambiguous = result.get("is_ambiguous", False)
    ambiguity_type = result.get("ambiguity_type")
    clarification_q = result.get("clarification_question")
    options = result.get("options", [])
    reasoning = result.get("reasoning", "")
    confidence = result.get("confidence", 1.0)

    # only treat it as ambiguous if the LLM is reasonably confident
    # low-confidence ambiguity flags are noise — just proceed
    if is_ambiguous and confidence < 0.6:
        logger.info(f"Ambiguity detected but low confidence ({confidence}), proceeding anyway")
        is_ambiguous = False

    if is_ambiguous:
        logger.info(f"Ambiguous ({ambiguity_type}): {clarification_q}")
        logger.info(f"Options: {options}")
        logger.info(f"Reasoning: {reasoning}")
    else:
        logger.info(f"Question is clear. Reasoning: {reasoning}")

    return {
        "is_ambiguous": is_ambiguous,
        "ambiguity_type": ambiguity_type or "",
        "clarification_question": clarification_q or "",
        "clarification_options": options or [],
    }
