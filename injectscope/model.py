"""A small logistic-regression classifier written from scratch (standard library only).

Author: Chandu Komme

Features
--------
* hashed character 3-5-grams of the canonical text (catches spelling tricks)
* hashed word unigrams and bigrams (catches phrasing)
* the same n-grams from decoded variants (split letters, base64, leetspeak),
  prefixed so the model can learn that "decoded text said X" is suspicious
* the numeric signals from :mod:`injectscope.rules`

Hashing uses ``zlib.crc32`` so results are identical across runs and machines
(Python's built-in ``hash`` is salted per process).

Training is plain stochastic gradient descent with L2 regularisation and a
seeded shuffle, so the same data always produces the same ``model.json``.
"""

from __future__ import annotations

import json
import math
import random
import re
import zlib
from pathlib import Path

from .rules import signals
from .text import canonical, variants

__author__ = "Chandu Komme"

DIM = 1 << 16
_WORD = re.compile(r"[^\W\d_]+|\d+", re.U)


def _bucket(feature: str) -> int:
    return zlib.crc32(feature.encode("utf-8")) % DIM


def ngram_features(text: str) -> dict[str, float]:
    """Named sparse features (before hashing), so they can be explained later."""
    feats: dict[str, float] = {}
    forms = {name: form for name, form in variants(text) if name != "reversed"}
    for name, form in forms.items():
        prefix = "" if name == "canonical" else f"{name}:"
        padded = f" {form} "
        if name == "canonical":
            for n in (3, 4, 5):
                for i in range(len(padded) - n + 1):
                    feats[f"c:{padded[i:i + n]}"] = 1.0
        words = _WORD.findall(form)
        for w in words:
            feats[f"{prefix}w:{w}"] = 1.0
        for a, b in zip(words, words[1:]):
            feats[f"{prefix}b:{a} {b}"] = 1.0
    norm = math.sqrt(len(feats)) or 1.0
    return {k: v / norm for k, v in feats.items()}


RULE_SIGNALS = ("rule_score", "rule_count")


def featurize(text: str, use_rules: bool = True) -> tuple[dict[str, float], dict[str, float]]:
    dense = {f"s:{k}": v for k, v in signals(text).items() if use_rules or k not in RULE_SIGNALS}
    return ngram_features(text), dense


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)
    return e / (1 + e)


class LogisticModel:
    def __init__(self, use_rules: bool = True) -> None:
        self.use_rules = use_rules
        self.w = [0.0] * DIM
        self.dense: dict[str, float] = {}
        self.bias = 0.0
        self.meta: dict = {}

    # ---- inference -------------------------------------------------------
    def _z(self, sparse: dict[str, float], dense: dict[str, float]) -> float:
        z = self.bias
        for name, value in sparse.items():
            z += self.w[_bucket(name)] * value
        for name, value in dense.items():
            z += self.dense.get(name, 0.0) * value
        return z

    def predict_proba(self, text: str) -> float:
        return _sigmoid(self._z(*featurize(text, self.use_rules)))

    def explain(self, text: str, top: int = 6) -> list[dict]:
        """The features that pushed this input hardest toward 'attack' or 'benign'."""
        sparse, dense = featurize(text, self.use_rules)
        parts = [(n, self.w[_bucket(n)] * v) for n, v in sparse.items()]
        parts += [(n, self.dense.get(n, 0.0) * v) for n, v in dense.items()]
        parts.sort(key=lambda p: -abs(p[1]))
        return [{"feature": n, "contribution": round(c, 4)} for n, c in parts[:top] if abs(c) > 1e-4]

    # ---- training --------------------------------------------------------
    def fit(self, texts: list[str], labels: list[int], *, epochs: int = 20, lr: float = 0.5,
            l2: float = 1e-4, seed: int = 7, rule_dropout: float = 0.5) -> "LogisticModel":
        """SGD training.

        ``rule_dropout`` hides the rule signals from a random share of examples in
        each epoch. Without it the rule score separates the training data almost
        perfectly, so the classifier ignores the wording and copies the rules,
        and then misses every paraphrase the rules miss.
        """
        rows = [featurize(t, self.use_rules) for t in texts]
        pos = sum(labels) or 1
        neg = (len(labels) - sum(labels)) or 1
        weight = {1: len(labels) / (2 * pos), 0: len(labels) / (2 * neg)}  # balance the classes
        order = list(range(len(rows)))
        rng = random.Random(seed)
        for epoch in range(epochs):
            rng.shuffle(order)
            step = lr / (1 + 0.3 * epoch)
            for i in order:
                sparse, dense = rows[i]
                if self.use_rules and rule_dropout and rng.random() < rule_dropout:
                    dense = {k: v for k, v in dense.items() if k[2:] not in RULE_SIGNALS}
                y = labels[i]
                g = (_sigmoid(self._z(sparse, dense)) - y) * weight[y]
                for name, value in sparse.items():
                    b = _bucket(name)
                    self.w[b] -= step * (g * value + l2 * self.w[b])
                for name, value in dense.items():
                    cur = self.dense.get(name, 0.0)
                    self.dense[name] = cur - step * (g * value + l2 * cur)
                self.bias -= step * g
        self.meta = {"epochs": epochs, "lr": lr, "l2": l2, "seed": seed, "examples": len(texts),
                     "rule_dropout": rule_dropout if self.use_rules else 0.0}
        return self

    # ---- persistence -----------------------------------------------------
    def to_dict(self) -> dict:
        sparse = {str(i): round(v, 5) for i, v in enumerate(self.w) if abs(v) >= 1e-4}
        return {"format": "injectscope-logreg/1", "dim": DIM, "use_rules": self.use_rules, "bias": round(self.bias, 6),
                "dense": {k: round(v, 6) for k, v in sorted(self.dense.items())},
                "sparse": sparse, "meta": self.meta}

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "LogisticModel":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("format") != "injectscope-logreg/1" or data.get("dim") != DIM:
            raise ValueError(f"{path} is not an InjectScope model for DIM={DIM}")
        model = cls(use_rules=data.get("use_rules", True))
        model.bias = data["bias"]
        model.dense = data["dense"]
        for i, v in data["sparse"].items():
            model.w[int(i)] = v
        model.meta = data.get("meta", {})
        return model


__all__ = ["LogisticModel", "featurize", "ngram_features", "DIM", "canonical"]
