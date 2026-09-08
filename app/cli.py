"""
CLI for quick testing.

Usage:
    python -m app.cli "What are the top 5 customers by revenue?"
    python -m app.cli "Show me revenue"  # will trigger clarification
"""

import sys
import json
import logging
from dotenv import load_dotenv

# load .env before anything else touches config
load_dotenv()

from app.agents.graph import pipeline
from app.agents.nodes.handle_clarification import handle_clarification
from app.observability.tracing import start_trace, end_trace, score_trace


def run(question: str) -> None:
    """run a question through the pipeline, handling clarification interactively."""

    print(f"\n{'='*60}")
    print(f"Question: {question}")
    print(f"{'='*60}\n")

    state = {
        "user_question": question,
        "sql_dialect": "sqlite",
    }

    # one Langfuse trace covers the whole question, including every
    # clarification round -- no-op if Langfuse isn't configured
    trace_token = start_trace("sqlpilot.query", session_id="cli", input=question)

    # the clarification loop lives here, not inside the graph
    # graph stops when it needs user input, we collect it, then re-invoke
    max_rounds = 3  # safety net
    for _ in range(max_rounds):
        result = pipeline.invoke(state)

        # check if the graph stopped for clarification
        if result.get("final_status") == "clarification_needed" and result.get("is_ambiguous"):
            clarification_q = result.get("clarification_question", "")
            options = result.get("clarification_options", [])
            round_num = result.get("clarification_round", 0) + 1

            print(f"--- Clarification needed (round {round_num}/2) ---")
            print(f"\n{clarification_q}\n")

            if options:
                for i, opt in enumerate(options, 1):
                    print(f"  ({i}) {opt}")
                print()

            # get user input
            try:
                user_input = input("Your answer: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nSkipping clarification, proceeding with best guess...")
                user_input = ""

            if not user_input:
                # user skipped — force proceed by exhausting the round budget
                state = dict(result)
                state["clarification_round"] = 2
                state["is_ambiguous"] = False
                state["final_status"] = ""
                continue

            # map number input to option text
            if options and user_input.isdigit():
                idx = int(user_input) - 1
                if 0 <= idx < len(options):
                    user_input = options[idx]

            # run handle_clarification to enrich the question
            enriched_state = dict(result)
            enriched_state["clarification_response"] = user_input
            updates = handle_clarification(enriched_state)

            # merge the updates into the state for the next graph invocation
            state = {**enriched_state, **updates}
            state["final_status"] = ""  # clear so the graph runs fresh
            continue

        # graph completed normally — done
        break

    _print_results(result)
    # ask for feedback while the trace is still active so the score attaches to it
    _collect_feedback()

    # quality metrics: how often did we need to self-correct or ask for
    # clarification? (see IMPLEMENTATION_PLAN.md Phase 7)
    end_trace(
        trace_token,
        output={
            "final_status": result.get("final_status"),
            "generated_sql": result.get("generated_sql"),
            "explanation": result.get("explanation"),
        },
        metadata={
            "clarification_rounds": result.get("clarification_round", 0),
            "validation_retry_count": result.get("validation_retry_count", 0),
            "execution_retry_count": result.get("execution_retry_count", 0),
            "self_correction_attempts": len(result.get("correction_history", [])),
        },
    )


def _collect_feedback() -> None:
    """ask for a thumbs up/down on the result and log it as a Langfuse score."""
    try:
        raw = input("Rate this response (1=good, 0=bad, enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if raw not in ("0", "1"):
        return

    score_trace("user_feedback", value=int(raw))
    print()


def _print_results(result: dict) -> None:
    """format and print the pipeline output."""

    sql = result.get("generated_sql", "")
    if sql:
        print(f"Generated SQL:\n{sql}\n")

    assumptions = result.get("llm_assumptions", "")
    if assumptions:
        print(f"Assumptions: {assumptions}\n")

    error = result.get("execution_error", "")
    if error:
        print(f"Execution Error: {error}\n")
    else:
        rows = result.get("query_results", [])
        columns = result.get("query_columns", [])
        print(f"Results: {len(rows)} row(s)")

        if rows:
            print(f"Columns: {', '.join(columns)}")
            print("-" * 60)
            for row in rows[:20]:
                print("  " + " | ".join(str(v) for v in row.values()))
            if len(rows) > 20:
                print(f"  ... and {len(rows) - 20} more rows")
        print()

    explanation = result.get("explanation", "")
    if explanation:
        print(f"Explanation:\n{explanation}\n")

    print(f"Status: {result.get('final_status', 'unknown')}")
    print(f"{'='*60}\n")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if len(sys.argv) < 2:
        print("Usage: python -m app.cli \"your question here\"")
        sys.exit(1)

    question = " ".join(sys.argv[1:])
    run(question)


if __name__ == "__main__":
    main()
