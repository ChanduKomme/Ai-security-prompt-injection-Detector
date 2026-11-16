"""CLI entrypoint: score the labeled dataset with the heuristic scanner, optionally the
model judge, and report precision/recall vs. ground truth side by side.

Offline mode:  python src/main.py --offline
Online mode:   python src/main.py            (requires ANTHROPIC_API_KEY)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "labeled_prompts.json"

sys.path.insert(0, str(ROOT))

from src.heuristics import scan  # noqa: E402
from src.model_judge import JudgeError, create_client, judge  # noqa: E402


def load_dataset() -> list[dict]:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def prf(tp: int, fp: int, fn: int) -> tuple[float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return round(precision, 3), round(recall, 3)


def summarize(rows: list[dict], prediction_key: str) -> dict:
    """Score classified rows and report how many received a verdict."""
    tp = fp = fn = tn = 0
    for row in rows:
        pred = row[prediction_key]
        if pred is None:
            continue
        truth = row["truth"] == "injection"
        if pred and truth:
            tp += 1
        elif pred and not truth:
            fp += 1
        elif not pred and truth:
            fn += 1
        else:
            tn += 1
    precision, recall = prf(tp, fp, fn)
    evaluated = tp + fp + fn + tn
    return {
        "precision": precision if evaluated else None,
        "recall": recall if evaluated else None,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "evaluated": evaluated,
        "total": len(rows),
        "rows": rows,
    }


def score_heuristic(dataset: list[dict]) -> dict:
    rows = []
    for row in dataset:
        result = scan(row["text"])
        rows.append({
            "id": row["id"],
            "truth": row["label"],
            "heuristic_flagged": result.is_flagged,
            "matched_patterns": result.matched_patterns,
        })
    return summarize(rows, "heuristic_flagged")


def score_model(dataset: list[dict], client=None) -> dict:
    if client is None:
        client = create_client()
    rows = []
    for row in dataset:
        try:
            verdict = judge(row["text"], client=client)
        except JudgeError as exc:
            prediction = {"model_flagged": None, "confidence": None, "error": str(exc)}
        else:
            prediction = {
                "model_flagged": verdict["is_injection"],
                "confidence": verdict["confidence"],
            }
        rows.append({"id": row["id"], "truth": row["label"], **prediction})
    return summarize(rows, "model_flagged")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prompt-injection detector: heuristic vs. model vs. ground truth")
    parser.add_argument("--offline", action="store_true", help="heuristic only, no API key needed")
    parser.add_argument("--json", action="store_true", help="print raw JSON instead of a table")
    args = parser.parse_args()

    dataset = load_dataset()
    heuristic = score_heuristic(dataset)

    model = None
    model_status = "offline"
    if not args.offline:
        model_status = "unavailable"
        try:
            model = score_model(dataset)
        except JudgeError as exc:
            print(f"Warning: {exc}", file=sys.stderr)
        else:
            evaluated = model["evaluated"]
            total = model["total"]
            if evaluated:
                model_status = "complete" if evaluated == total else "partial"
            if model_status != "complete":
                print(f"Warning: Claude evaluated {evaluated} of {total} prompts.", file=sys.stderr)

    if args.json:
        print(json.dumps({"heuristic": heuristic, "model": model, "model_status": model_status}, indent=2))
        return 0

    print(f"Loaded {len(dataset)} labeled prompts")
    print(f"Model status: {model_status}\n")
    print(f"{'Method':<12}{'Precision':<12}{'Recall':<10}{'TP':<5}{'FP':<5}{'FN':<5}{'TN':<5}Scored")
    summaries = [("heuristic", heuristic)]
    if model is not None and model["evaluated"]:
        summaries.append(("model", model))
    for method, result in summaries:
        precision = "n/a" if result["precision"] is None else f"{result['precision']:.3f}"
        recall = "n/a" if result["recall"] is None else f"{result['recall']:.3f}"
        print(
            f"{method:<12}{precision:<12}{recall:<10}"
            f"{result['tp']:<5}{result['fp']:<5}{result['fn']:<5}{result['tn']:<5}"
            f"{result['evaluated']}/{result['total']}"
        )

    missed_ids = [
        row["id"] for row in heuristic["rows"]
        if row["truth"] == "injection" and not row["heuristic_flagged"]
    ]
    if missed_ids:
        print(f"\nHeuristic missed {len(missed_ids)} labeled injection(s): {', '.join(missed_ids)}")
        if model is not None:
            checked = [
                row for row in model["rows"]
                if row["id"] in missed_ids and row["model_flagged"] is not None
            ]
            if checked:
                caught = sum(row["model_flagged"] for row in checked)
                print(f"Model flagged {caught} of the {len(checked)} heuristic misses it evaluated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
