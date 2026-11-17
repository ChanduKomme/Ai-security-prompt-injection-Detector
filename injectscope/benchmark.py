"""Benchmark rules-only vs model-only vs hybrid on every evaluation set.

Author: Chandu Komme

Sets
----
* ``cv``    5-fold out-of-fold predictions on the training data (model modes)
* ``test``  held-out 20% split from the same generator as training
* ``hard``  72 hand-written cases (paraphrases, fiction wrappers, hard negatives)
* ``blind``  50 hand-written cases frozen before the classifier existed. Its
             first result exposed a design flaw, which was then fixed, so it
             now counts as *seen during development*.
* ``blind2`` 60 new hand-written cases frozen after that fix and before the
             re-run; the most honest number in this report.

Both blind files have committed SHA-256 checksums.

``test`` shares templates with training, so it is an optimistic number.
``hard`` and ``blind`` are the honest measure of generalisation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .detector import Detector
from .metrics import percentile, roc_auc, scores, sweep
from .train import ROOT, load, out_of_fold

__author__ = "Chandu Komme"

DATA = ROOT / "data"
SETS = ("test", "hard", "blind", "blind2")
GATES = {  # minimum hybrid scores; CI fails below these
    "test": {"f1": 0.95, "fpr_max": 0.03},
    "hard": {"f1": 0.85, "fpr_max": 0.10},
    "blind": {"f1": 0.75, "fpr_max": 0.15},
    "blind2": {"f1": 0.75, "fpr_max": 0.15},
}


def verify_blind() -> bool:
    for name in ("blind", "blind2"):
        expected = (DATA / f"{name}.sha256").read_text().split()[0]
        if hashlib.sha256((DATA / f"{name}.jsonl").read_bytes()).hexdigest() != expected:
            return False
    return True


def evaluate(detector: Detector, rows: list[dict]) -> dict:
    labels, preds, probs, latency, mistakes = [], [], [], [], []
    by_cat: dict[str, list[int]] = {}
    for row in rows:
        res = detector.scan(row["text"])
        labels.append(row["label"])
        preds.append(int(res.is_attack))
        probs.append(res.score)
        latency.append(res.latency_ms)
        by_cat.setdefault(f'{"attack" if row["label"] else "benign"}/{row["category"]}', []).append(
            int(res.is_attack) == row["label"])
        if int(res.is_attack) != row["label"]:
            mistakes.append({"id": row["id"], "label": row["label"], "score": res.score,
                             "category": row["category"], "text": row["text"][:120]})
    return {
        **scores(labels, preds), "auc": roc_auc(labels, probs), "n": len(rows),
        "latency_ms": {"p50": percentile(latency, 0.5), "p95": percentile(latency, 0.95)},
        "per_category": {k: round(sum(v) / len(v), 3) for k, v in sorted(by_cat.items())},
        "sweep": sweep(labels, probs), "mistakes": mistakes,
    }


def run(out_dir: str | Path = ROOT / "reports") -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    train_rows = load(DATA / "train.jsonl")
    labels = [r["label"] for r in train_rows]
    report = {"blind_set_unchanged": verify_blind(), "modes": {}}
    for mode in Detector.MODES:
        det = Detector(mode)
        entry = {"threshold": det.threshold}
        if mode != "rules":
            oof = out_of_fold(train_rows, use_rules=(mode == "hybrid"))
            entry["cv"] = {**scores(labels, [int(p >= det.threshold) for p in oof]), "auc": roc_auc(labels, oof)}
        for name in SETS:
            entry[name] = evaluate(det, load(DATA / f"{name}.jsonl"))
        report["modes"][mode] = entry
    report["gate"] = gate(report)
    (out / "benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / "benchmark.md").write_text(markdown(report), encoding="utf-8")
    return report


def gate(report: dict) -> dict:
    failures = []
    if not report["blind_set_unchanged"]:
        failures.append("blind set checksum mismatch")
    hybrid = report["modes"]["hybrid"]
    for name, rule in GATES.items():
        if hybrid[name]["f1"] < rule["f1"]:
            failures.append(f"{name}: F1 {hybrid[name]['f1']} < {rule['f1']}")
        if hybrid[name]["fpr"] > rule["fpr_max"]:
            failures.append(f"{name}: FPR {hybrid[name]['fpr']} > {rule['fpr_max']}")
    return {"passed": not failures, "failures": failures, "thresholds": GATES}


def markdown(report: dict) -> str:
    lines = ["# InjectScope benchmark", "",
             f"Blind set checksum verified: **{report['blind_set_unchanged']}**", "",
             "| Mode | Set | Precision | Recall | F1 | FPR | AUC | p95 ms |", "|---|---|---|---|---|---|---|---|"]
    for mode, entry in report["modes"].items():
        if "cv" in entry:
            cv = entry["cv"]
            lines.append(f"| {mode} | cv (5-fold) | {cv['precision']} | {cv['recall']} | {cv['f1']} | {cv['fpr']} | {cv['auc']} | |")
        for name in SETS:
            e = entry[name]
            lines.append(f"| {mode} | {name} | {e['precision']} | {e['recall']} | {e['f1']} | {e['fpr']} | "
                         f"{e['auc']} | {e['latency_ms']['p95']} |")
    hybrid = report["modes"]["hybrid"]
    for name in ("hard", "blind2"):
        lines += ["", f"## Hybrid: per-category accuracy on `{name}`", "", "| Category | Accuracy |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in hybrid[name]["per_category"].items()]
        lines += ["", f"### Hybrid mistakes on `{name}`", ""]
        lines += [f"- `{m['id']}` ({'attack' if m['label'] else 'benign'}/{m['category']}, score {m['score']}): "
                  f"{m['text']}" for m in hybrid[name]["mistakes"]] or ["- none"]
    lines += ["", "## Hybrid threshold sweep on `hard`", "", "| Threshold | Precision | Recall | F1 | FPR |", "|---|---|---|---|---|"]
    lines += [f"| {s['threshold']} | {s['precision']} | {s['recall']} | {s['f1']} | {s['fpr']} |" for s in hybrid["hard"]["sweep"]]
    g = report["gate"]
    lines += ["", f"## Gate: {'PASSED' if g['passed'] else 'FAILED'}", ""]
    lines += [f"- {f}" for f in g["failures"]] or ["- all thresholds met"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    result = run()
    print(markdown(result))
    raise SystemExit(0 if result["gate"]["passed"] else 1)
