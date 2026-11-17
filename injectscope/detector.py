"""The hybrid detector: rules + classifier (+ optional judge).

Author: Chandu Komme

Decision flow
-------------
1. Run the rules on every text variant (canonical, leetspeak, split letters,
   reversed, decoded base64).
2. Score with the classifier, which sees the n-grams *and* the rule signals.
3. A strong rule (weight >= 0.8) that fired on a *decoded* variant is decisive:
   nobody hides harmless text in base64 or backwards writing.
4. If the score is inside the uncertain band and a judge is configured, the
   judge decides; if the judge fails, the detector keeps its own verdict.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from .judge import AnthropicJudge
from .model import LogisticModel
from .rules import match_rules, rule_score

__author__ = "Chandu Komme"

MODEL_PATHS = {"hybrid": Path(__file__).with_name("model.json"),
               "model": Path(__file__).with_name("model_text.json")}
DECODED = {"base64", "reversed", "split_letters"}


@dataclass
class Result:
    verdict: str
    score: float
    threshold: float
    mode: str
    rule_score: float
    model_score: Optional[float]
    rules: list[dict] = field(default_factory=list)
    top_features: list[dict] = field(default_factory=list)
    judge: Optional[dict] = None
    latency_ms: float = 0.0

    @property
    def is_attack(self) -> bool:
        return self.verdict == "attack"

    def to_dict(self) -> dict:
        return asdict(self)


class Detector:
    MODES = ("rules", "model", "hybrid")

    def __init__(self, mode: str = "hybrid", model: LogisticModel | None = None,
                 threshold: float | None = None, band: float = 0.15, judge: AnthropicJudge | None = None,
                 model_path: str | Path | None = None) -> None:
        if mode not in self.MODES:
            raise ValueError(f"mode must be one of {self.MODES}")
        self.mode = mode
        self.model = model
        if self.model is None and mode != "rules":
            self.model = LogisticModel.load(model_path or MODEL_PATHS[mode])
        self.threshold = threshold if threshold is not None else self._default_threshold()
        self.band = band
        self.judge = judge

    def _default_threshold(self) -> float:
        if self.mode == "rules" or self.model is None:
            return 0.5
        return float(self.model.meta.get("threshold", 0.5))

    def scan(self, text: str) -> Result:
        started = time.perf_counter()
        hits = match_rules(text)
        r_score = rule_score(hits)
        m_score = self.model.predict_proba(text) if self.mode != "rules" else None

        if self.mode == "rules":
            score = r_score
        elif self.mode == "model":
            score = m_score
        else:
            score = m_score
            if any(h.weight >= 0.8 and h.variant in DECODED for h in hits):
                score = max(score, 0.99)

        verdict = "attack" if score >= self.threshold else "benign"
        judged = None
        if self.judge and self.mode == "hybrid" and abs(score - self.threshold) < self.band:
            answer = self.judge.judge(text)
            if answer is not None:
                judged = {"attack": answer.attack, "confidence": answer.confidence, "reason": answer.reason}
                verdict = "attack" if answer.attack else "benign"

        return Result(
            verdict=verdict, score=round(score, 4), threshold=round(self.threshold, 4), mode=self.mode,
            rule_score=r_score, model_score=None if m_score is None else round(m_score, 4),
            rules=[{"id": h.rule, "family": h.family, "owasp": h.owasp, "weight": h.weight,
                    "variant": h.variant, "evidence": h.evidence, "why": h.why} for h in hits],
            top_features=self.model.explain(text) if self.model is not None and self.mode != "rules" else [],
            judge=judged, latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )
