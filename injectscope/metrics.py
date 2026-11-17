"""Evaluation metrics, implemented directly so every number is auditable.

Author: Chandu Komme
"""

from __future__ import annotations

__author__ = "Chandu Komme"


def confusion(labels: list[int], preds: list[int]) -> dict[str, int]:
    tp = sum(1 for y, p in zip(labels, preds) if y and p)
    fp = sum(1 for y, p in zip(labels, preds) if not y and p)
    fn = sum(1 for y, p in zip(labels, preds) if y and not p)
    tn = sum(1 for y, p in zip(labels, preds) if not y and not p)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def scores(labels: list[int], preds: list[int]) -> dict[str, float]:
    c = confusion(labels, preds)
    precision = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else 0.0
    recall = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    fpr = c["fp"] / (c["fp"] + c["tn"]) if c["fp"] + c["tn"] else 0.0
    accuracy = (c["tp"] + c["tn"]) / len(labels) if labels else 0.0
    return {**c, "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
            "fpr": round(fpr, 4), "accuracy": round(accuracy, 4)}


def roc_auc(labels: list[int], probs: list[float]) -> float:
    """Probability that a random attack scores above a random benign input (ties count half)."""
    pos = [p for y, p in zip(labels, probs) if y]
    neg = [p for y, p in zip(labels, probs) if not y]
    if not pos or not neg:
        return float("nan")
    ranked = sorted(probs)
    rank: dict[float, float] = {}
    i = 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j] == ranked[i]:
            j += 1
        rank[ranked[i]] = (i + j + 1) / 2  # average 1-based rank of the tie group
        i = j
    rank_sum = sum(rank[p] for p in pos)
    return round((rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)), 4)


def best_threshold(labels: list[int], probs: list[float]) -> float:
    """Middle of the threshold range that reaches the best F1.

    When the classes separate cleanly many thresholds tie; taking the middle of
    that range leaves the most margin on both sides for unseen data.
    """
    grid = [step / 100 for step in range(5, 96)]
    f1s = [scores(labels, [int(p >= t) for p in probs])["f1"] for t in grid]
    top = max(f1s)
    best = [t for t, f in zip(grid, f1s) if f == top]
    return best[len(best) // 2]


def sweep(labels: list[int], probs: list[float], points=(0.3, 0.4, 0.5, 0.6, 0.7, 0.8)) -> list[dict]:
    return [{"threshold": t, **scores(labels, [int(p >= t) for p in probs])} for t in points]


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo), 4)
