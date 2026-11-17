"""Train the two classifiers and pick their thresholds without touching test data.

Author: Chandu Komme

The decision threshold is chosen from *out-of-fold* predictions on the training
set (5-fold, stratified, seeded). The test, hard and blind sets are never seen
during training or threshold selection.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from .metrics import best_threshold, roc_auc, scores
from .model import LogisticModel

__author__ = "Chandu Komme"

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = Path(__file__).resolve().parent


def load(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def folds(rows: list[dict], k: int = 5, seed: int = 11) -> list[list[int]]:
    """Stratified k-fold indices: each fold keeps the attack/benign ratio."""
    rng = random.Random(seed)
    buckets: list[list[int]] = [[] for _ in range(k)]
    for label in (0, 1):
        idx = [i for i, r in enumerate(rows) if r["label"] == label]
        rng.shuffle(idx)
        for n, i in enumerate(idx):
            buckets[n % k].append(i)
    return buckets


def out_of_fold(rows: list[dict], use_rules: bool, k: int = 5) -> list[float]:
    probs = [0.0] * len(rows)
    for held in folds(rows, k):
        held_set = set(held)
        train = [r for i, r in enumerate(rows) if i not in held_set]
        model = LogisticModel(use_rules).fit([r["text"] for r in train], [r["label"] for r in train])
        for i in held:
            probs[i] = model.predict_proba(rows[i]["text"])
    return probs


def train(train_path: str | Path = ROOT / "data" / "train.jsonl", out_dir: str | Path = PACKAGE) -> dict:
    rows = load(train_path)
    labels = [r["label"] for r in rows]
    summary = {}
    for name, use_rules in (("model.json", True), ("model_text.json", False)):
        oof = out_of_fold(rows, use_rules)
        threshold = best_threshold(labels, oof)
        cv = scores(labels, [int(p >= threshold) for p in oof])
        model = LogisticModel(use_rules).fit([r["text"] for r in rows], labels)
        model.meta.update({"threshold": threshold, "cv_f1": cv["f1"], "cv_auc": roc_auc(labels, oof),
                           "trained_on": Path(train_path).name})
        model.save(Path(out_dir) / name)
        summary[name] = model.meta
    return summary


if __name__ == "__main__":
    print(json.dumps(train(), indent=2))
