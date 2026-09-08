"""
Evaluation harness -- runs tests/eval/dataset.json through the live pipeline
and reports execution accuracy, clarification precision/recall, and latency.

See IMPLEMENTATION_PLAN.md Phase 9. This hits the real LLM provider and the
real demo DB, so it's a standalone script rather than a pytest suite:

    python scripts/run_eval.py
"""

import json
import statistics
import time
from collections import Counter
from pathlib import Path

from app.agents.graph import pipeline
from app.db.connection import SQLiteConnector

DATASET_PATH = Path(__file__).parent / "dataset.json"


def load_dataset() -> list[dict]:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def _row_multiset(row: dict) -> Counter:
    """a row's values as a multiset, order/column-name-independent, floats rounded."""
    values = []
    for v in row.values():
        if isinstance(v, float):
            v = round(v, 2)
        values.append(v)
    return Counter(values)


def rows_match(generated: list[dict], gold: list[dict]) -> bool:
    """
    compare two result sets the way execution-accuracy evals usually do:
    same row count, and every gold row's values must appear (as a subset,
    respecting duplicate counts) within some not-yet-matched generated row.

    this makes `SELECT SUM(x) AS mrr` compare equal to
    `SELECT SUM(x) AS monthly_recurring_revenue`, row/column order not
    matter, and -- deliberately -- `SELECT c.*` compare equal to
    `SELECT c.id, c.name` as long as every gold column's value is present:
    an LLM answering "which customers..." with extra columns is still a
    correct answer, not a wrong one.
    """
    if len(generated) != len(gold):
        return False

    gen_multisets = [_row_multiset(r) for r in generated]
    used = [False] * len(gen_multisets)

    for gold_row in gold:
        gold_values = _row_multiset(gold_row)
        matched_index = None
        for i, cand in enumerate(gen_multisets):
            if used[i]:
                continue
            if all(cand[val] >= count for val, count in gold_values.items()):
                matched_index = i
                break
        if matched_index is None:
            return False
        used[matched_index] = True

    return True


def _execute(sql: str) -> list[dict]:
    db = SQLiteConnector()
    return db.execute_query(sql)["rows"]


def run_case(case: dict) -> dict:
    """run one eval case through the pipeline and score it."""
    # unique session_id per case so the shared rate limiter (20/min by
    # default) doesn't reject cases when running the full eval set back to back
    state = {
        "user_question": case["question"],
        "sql_dialect": "sqlite",
        "session_id": f"eval-{case['id']}",
    }

    start = time.time()
    try:
        result = pipeline.invoke(state)
    except Exception as e:
        # a provider outage/quota exhaustion shouldn't lose every other case's
        # results -- record it as a failure for this case and keep going
        return {
            "id": case["id"],
            "category": case["category"],
            "question": case["question"],
            "expect_ambiguous": case["category"] == "ambiguous",
            "flagged_ambiguous": False,
            "latency_s": round(time.time() - start, 2),
            "correct": False,
            "note": f"pipeline raised {type(e).__name__}: {e}",
        }
    latency_s = time.time() - start

    flagged_ambiguous = (
        result.get("final_status") == "clarification_needed" and result.get("is_ambiguous", False)
    )
    expect_ambiguous = case["category"] == "ambiguous"

    base = {
        "id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "expect_ambiguous": expect_ambiguous,
        "flagged_ambiguous": flagged_ambiguous,
        "latency_s": round(latency_s, 2),
    }

    if expect_ambiguous:
        base["correct"] = flagged_ambiguous
        if flagged_ambiguous:
            base["clarification_question"] = result.get("clarification_question", "")
        return base

    if flagged_ambiguous:
        base["correct"] = False
        base["note"] = "false positive: flagged as ambiguous when a gold SQL answer was expected"
        base["clarification_question"] = result.get("clarification_question", "")
        return base

    if result.get("final_status") != "success":
        base["correct"] = False
        base["note"] = result.get("explanation") or result.get("execution_error") or "pipeline did not reach success"
        base["generated_sql"] = result.get("generated_sql", "")
        return base

    generated_sql = result.get("generated_sql", "")
    gen_rows = result.get("query_results", [])
    try:
        gold_rows = _execute(case["gold_sql"])
    except RuntimeError as e:
        raise RuntimeError(f"gold_sql for case {case['id']} failed to execute: {e}") from e

    match = rows_match(gen_rows, gold_rows)
    base["correct"] = match
    base["generated_sql"] = generated_sql
    base["gold_sql"] = case["gold_sql"]
    if not match:
        base["generated_result_preview"] = gen_rows[:5]
        base["gold_result_preview"] = gold_rows[:5]

    return base


def run_eval(dataset: list[dict] | None = None, on_case_done=None) -> dict:
    """run every case and return {results: [...], summary: {...}}."""
    dataset = dataset if dataset is not None else load_dataset()

    results = []
    for case in dataset:
        r = run_case(case)
        results.append(r)
        if on_case_done:
            on_case_done(r)

    return {"results": results, "summary": summarize(results)}


def summarize(results: list[dict]) -> dict:
    non_ambiguous = [r for r in results if not r["expect_ambiguous"]]
    ambiguous = [r for r in results if r["expect_ambiguous"]]

    execution_correct = sum(1 for r in non_ambiguous if r["correct"])
    execution_accuracy = execution_correct / len(non_ambiguous) if non_ambiguous else None

    true_positives = sum(1 for r in ambiguous if r["flagged_ambiguous"])
    false_negatives = len(ambiguous) - true_positives
    false_positives = sum(1 for r in non_ambiguous if r["flagged_ambiguous"])

    clarification_recall = true_positives / len(ambiguous) if ambiguous else None
    denom = true_positives + false_positives
    clarification_precision = true_positives / denom if denom else None

    latencies = [r["latency_s"] for r in results]

    by_category = {}
    for r in non_ambiguous:
        cat = r["category"]
        bucket = by_category.setdefault(cat, {"total": 0, "correct": 0})
        bucket["total"] += 1
        bucket["correct"] += int(r["correct"])

    return {
        "total_cases": len(results),
        "execution_accuracy": execution_accuracy,
        "execution_accuracy_by_category": {
            cat: b["correct"] / b["total"] for cat, b in by_category.items()
        },
        "clarification_recall": clarification_recall,
        "clarification_precision": clarification_precision,
        "clarification_true_positives": true_positives,
        "clarification_false_negatives": false_negatives,
        "clarification_false_positives": false_positives,
        "latency_seconds": {
            "mean": round(statistics.mean(latencies), 2),
            "median": round(statistics.median(latencies), 2),
            "p95": round(sorted(latencies)[int(len(latencies) * 0.95) - 1], 2),
            "max": round(max(latencies), 2),
        },
    }
