"""
CLI for quick testing.

Usage:
    python -m app.cli "What are the top 5 customers by revenue?"
    python -m app.cli "How many active subscriptions do we have?"
"""

import sys
import json
import logging
from dotenv import load_dotenv

# load .env before anything else touches config
load_dotenv()

from app.agents.graph import pipeline


def run(question: str) -> None:
    """run a question through the pipeline and print the results."""

    print(f"\n{'='*60}")
    print(f"Question: {question}")
    print(f"{'='*60}\n")

    # invoke the LangGraph pipeline
    result = pipeline.invoke({
        "user_question": question,
        "sql_dialect": "sqlite",
    })

    # show the generated SQL
    sql = result.get("generated_sql", "")
    print(f"Generated SQL:\n{sql}\n")

    # show assumptions if any
    assumptions = result.get("llm_assumptions", "")
    if assumptions:
        print(f"Assumptions: {assumptions}\n")

    # show execution status
    error = result.get("execution_error", "")
    if error:
        print(f"Execution Error: {error}\n")
    else:
        rows = result.get("query_results", [])
        columns = result.get("query_columns", [])
        print(f"Results: {len(rows)} row(s)")

        if rows:
            # print as a simple table
            print(f"Columns: {', '.join(columns)}")
            print("-" * 60)
            for row in rows[:20]:  # only show first 20
                print("  " + " | ".join(str(v) for v in row.values()))
            if len(rows) > 20:
                print(f"  ... and {len(rows) - 20} more rows")
        print()

    # show the explanation
    explanation = result.get("explanation", "")
    if explanation:
        print(f"Explanation:\n{explanation}\n")

    print(f"Status: {result.get('final_status', 'unknown')}")
    print(f"{'='*60}\n")


def main():
    # set up logging
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
