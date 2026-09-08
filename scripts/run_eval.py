"""
Run the evaluation dataset (tests/eval/dataset.json) through the live
pipeline and report execution accuracy, clarification precision/recall, and
latency.

    python scripts/run_eval.py

Hits the real LLM provider and the real demo DB for every case, so it's not
part of the pytest suite -- run it on demand. Saves a full per-case report to
tests/eval/results/<timestamp>.json and prints a summary.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# make sure we can import the app + tests packages when running this script directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from tests.eval.harness import run_eval

RESULTS_DIR = Path(__file__).parent.parent / "tests" / "eval" / "results"


def _on_case_done(r: dict) -> None:
    mark = "PASS" if r["correct"] else "FAIL"
    print(f"  [{mark}] {r['id']:5} ({r['category']:20}) {r['latency_s']:5.1f}s  {r['question']}")
    if not r["correct"] and r.get("note"):
        print(f"         note: {r['note']}")


def main() -> None:
    print(f"Running eval dataset...\n")
    report = run_eval(on_case_done=_on_case_done)
    summary = report["summary"]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"{timestamp}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"\n{'=' * 60}")
    print("Summary")
    print(f"{'=' * 60}")
    acc = summary["execution_accuracy"]
    print(f"Execution accuracy:        {acc:.1%}" if acc is not None else "Execution accuracy:        n/a")
    for cat, rate in summary["execution_accuracy_by_category"].items():
        print(f"  - {cat:20} {rate:.1%}")

    recall = summary["clarification_recall"]
    precision = summary["clarification_precision"]
    print(f"Clarification recall:      {recall:.1%}" if recall is not None else "Clarification recall:      n/a")
    print(f"Clarification precision:   {precision:.1%}" if precision is not None else "Clarification precision:   n/a")
    print(
        f"  (TP={summary['clarification_true_positives']}, "
        f"FN={summary['clarification_false_negatives']}, "
        f"FP={summary['clarification_false_positives']})"
    )

    lat = summary["latency_seconds"]
    print(f"Latency (s):                mean={lat['mean']}  median={lat['median']}  p95={lat['p95']}  max={lat['max']}")
    print(f"\nFull report saved to {out_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)  # quiet the pipeline's own INFO logs during eval
    main()
