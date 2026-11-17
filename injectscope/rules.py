"""Explainable detection rules and numeric signals.

Author: Chandu Komme

Rules look for intent, not single words. "Ignore" alone is harmless ("ignore
the typos"); "ignore" followed by a reference to prior *instructions* is an
override. Each rule has a weight from 0 to 1, an OWASP Top 10 for LLM
Applications (2025) mapping, and records which text variant it matched in
(for example ``base64`` or ``reversed``), so every alert explains itself.

Rule evidence combines with a noisy-OR: ``1 - prod(1 - weight)``.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from .text import entropy, script_mix, variants

__author__ = "Chandu Komme"


def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.I | re.S)


PRIOR = r"(?:previous|prior|above|earlier|preceding|original|initial|existing|old|former)"
GUIDANCE = r"(?:instructions?|rules|guidelines|guidance|directions|directives|prompts?|constraints|polic(?:y|ies)|system message|safeguards?|safety (?:rules|policy))"
NEGATE = r"(?:ignore|disregard|forget|override|set aside|drop|abandon|discard|skip|throw out|pay no attention to|bypass|disable|turn off|deactivate)"


@dataclass(frozen=True)
class Rule:
    id: str
    family: str
    owasp: str
    weight: float
    pattern: re.Pattern
    why: str


RULES: tuple[Rule, ...] = (
    Rule("R01", "override", "LLM01", 0.85,
         _rx(rf"\b{NEGATE}\b(?:\s+\w+){{0,4}}?\s+{PRIOR}\s+(?:\w+\s+){{0,2}}{GUIDANCE}"),
         "tells the model to drop its earlier instructions"),
    Rule("R02", "override", "LLM01", 0.75,
         _rx(rf"\b{NEGATE}\b\s+(?:your|the|all|any)\s+(?:\w+\s+){{0,2}}{GUIDANCE}"),
         "tells the model to drop its rules or safety policy"),
    Rule("R03", "override", "LLM01", 0.6,
         _rx(r"\bfrom now on,?\s+(?:you|your)\b|\bnew (?:system )?instructions?\s*[:\-]|\bupdated system instructions\b"
             r"|\byour (?:real|actual|new) (?:task|job|instructions?)\b|\bthe real instructions\b|\bguidance you received earlier is\b"),
         "replaces the model's instructions"),
    Rule("R04", "extraction", "LLM07", 0.8,
         _rx(r"\b(?:reveal|print|show|output|repeat|display|leak|dump|tell me|write out|recite|share|paste|quote)\b.{0,40}?"
             r"\b(?:your|the)\s+(?:\w+\s+){0,2}(?:system|hidden|initial|secret|original|internal|developer|exact|full)\s+"
             r"(?:prompt|instructions?|configuration|rules|preamble|message)"),
         "asks for the hidden system prompt"),
    Rule("R05", "extraction", "LLM07", 0.65,
         _rx(r"\b(?:text|message|instructions?)\s+(?:you were|you've been)\s+(?:initiali[sz]ed|given|configured)\s+with\b"
             r"|\bexactly as it appears in your (?:configuration|setup|prompt)\b|\bmessage before my first message\b"
             r"|\binstructions your developers gave you\b|\bsecret rules it was given\b"),
         "asks for the model's configuration indirectly"),
    Rule("R06", "jailbreak", "LLM01", 0.8,
         _rx(r"\b(?:dan|stan|aim|omega|evilbot)\b.{0,60}\b(?:no rules|never refuses|anything|unfiltered|without)\b"
             r"|\b(?:you are now in|you're now in|you are in|enter|entering|activate|switch (?:in)?to|now in)\s+(?:\w+\s+)?(?:developer|god|jailbreak|unrestricted) mode\b"
             r"|\b(?:jailbreak(?:en|ed)? (?:mode|enabled)|jailbreak[- ]mode|do anything now)\b"
             r"|\b(?:unfiltered|uncensored|unrestricted|rogue|jailbroken)\s+(?:model|ai|assistant|chatbot|alter ego|version)\b"),
         "invokes a jailbreak persona or mode"),
    Rule("R07", "jailbreak", "LLM01", 0.6,
         _rx(r"\b(?:no|zero|without (?:any )?)\s*(?:rules|restrictions|limitations|limits|filters|ethics|safety training)\b"
             r"|\bignores? (?:all )?(?:content )?polic(?:y|ies)\b|\bstay in (?:character|role)\b.{0,80}\b(?:anything|everything|no matter)\b"
             r"|\bnever refuse\b|\bhas broken free\b"),
         "asks the model to operate without limits"),
    Rule("R08", "indirect", "LLM01", 0.75,
         _rx(r"<!--.{0,300}?(?:\bai\b|assistant|model|instruction).{0,300}?-->|\[system\]\s*:|<\|im_start\|>|\[/?inst\]"
             r"|###\s*instruction|(?:note to|attention|hey) (?:the )?(?:ai|assistant|model|llm|ai model)\b"
             r"|\bassistant override\b|---\s*end user\s*---|\b(?:ai|assistant|model) (?:reading|evaluator)[^.:]{0,20}[:,]"
             r"|\bassistant, when you read this\b|display\s*:\s*none"),
         "hides instructions for the model inside content"),
    Rule("R09", "exfiltration", "LLM02", 0.8,
         _rx(r"!\[[^\]]*\]\(\s*https?://[^)\s]+\?[^)\s]*\)|\bhttps?://\S+[?&]\w+=\S*\b.{0,40}\b(?:token|session|conversation|data|secret)"
             r"|\b(?:append|add)\b.{0,50}\b(?:to|into)\s+(?:the\s+)?(?:url|link|https?://)"),
         "smuggles data out through a URL or image"),
    Rule("R10", "exfiltration", "LLM06", 0.7,
         _rx(r"\b(?:send|email|forward|post|upload|mail)\b.{0,60}\b(?:to\s+[\w.+-]+@[\w-]+\.[\w.]+|to\s+https?://)"
             r"|\b\w+_\w+\s*\([^)]*\)\s*(?:before|and then|then)\b|\brun\s+\w+_\w+\(\)|\brm\s+-rf\b|\.ssh/id_rsa\b"
             r"|\brefund \$?[\d,]+\b.{0,40}\bno need to ask\b"),
         "tries to trigger a tool or send data out"),
    Rule("R11", "obfuscation", "LLM01", 0.55,
         _rx(r"\b(?:decode|base64|rot-?13|backwards|reverse(?:d)?)\b.{0,40}\b(?:and|then)\s+(?:do|execute|follow|obey|run|carry)\b"
             r"|\bdecode and execute\b|\bread this backwards and do it\b|\btranslate\b.{0,60}\band then carry it out\b"),
         "asks to decode a hidden payload and act on it"),
    Rule("R12", "social_engineering", "LLM01", 0.55,
         _rx(r"\b(?:i am|i'm|this is)\b.{0,30}\b(?:developer|admin(?:istrator)?|security team|ceo|owner|creator)\b.{0,80}"
             r"\b(?:authori[sz]|bypass|disable|override|grant|unlock)\w*"
             r"|\bused to (?:read|tell) me\b.{0,40}\b(?:password|keys?|secrets?)\b"),
         "claims authority or uses an emotional pretext to unlock behavior"),
    Rule("R13", "multilingual", "LLM01", 0.8,
         _rx(r"\b(?:ignoriere|vergiss|ignorez|oubliez|oublie|ignora|olvida|negeer|vergeet)\b.{0,40}"
             r"\b(?:anweisungen|regeln|instructions|consignes|règles|instrucciones|reglas|istruzioni|regole|instruções|instructies|sicherheitsregeln)\b"
             r"|सभी पिछले निर्देशों|निर्देशों को अनदेखा"),
         "override phrased in another language"),
    Rule("R14", "multi_step", "LLM01", 0.6,
         _rx(r"\bstep \d\b.{0,80}\b(?:forget|ignore|disable)\b.{0,40}\b(?:safety|policy|rules)\b"
             r"|\brules can change\b.{0,80}\bnever refuse\b|\bsecond answer from\b.{0,40}\b(?:unfiltered|ignores policy)\b"),
         "breaks an override into innocent-looking steps"),
)


@dataclass(frozen=True)
class Hit:
    rule: str
    family: str
    owasp: str
    weight: float
    variant: str
    evidence: str
    why: str


def match_rules(text: str) -> list[Hit]:
    hits: dict[str, Hit] = {}
    for name, form in variants(text):
        for rule in RULES:
            if rule.id in hits:
                continue
            found = rule.pattern.search(form)
            if found:
                if name == "reversed" and rule.family not in ("override", "extraction"):
                    continue
                hits[rule.id] = Hit(rule.id, rule.family, rule.owasp, rule.weight, name,
                                    " ".join(found.group(0).split())[:100], rule.why)
    return sorted(hits.values(), key=lambda h: (-h.weight, h.rule))


def rule_score(hits: list[Hit]) -> float:
    remaining = 1.0
    for hit in hits:
        remaining *= 1 - hit.weight
    return round(1 - remaining, 4)


def signals(text: str) -> dict[str, float]:
    """Numeric features for the classifier, each scaled to roughly 0..1."""
    tokens = text.split()
    long_tokens = [t for t in tokens if len(t) >= 20]
    hits = match_rules(text)
    return {
        "rule_score": rule_score(hits),
        "rule_count": min(len(hits), 4) / 4,
        "invisible_chars": min(sum(text.count(c) for c in "​‌‍⁠﻿"), 10) / 10,
        "script_mix": script_mix(text),
        "high_entropy_token": 1.0 if any(entropy(t) > 4.2 for t in long_tokens) else 0.0,
        "url_with_query": 1.0 if re.search(r"https?://\S+\?\S+=", text) else 0.0,
        "email_address": 1.0 if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text) else 0.0,
        "code_call": 1.0 if re.search(r"\b\w+_\w+\s*\(", text) else 0.0,
        "role_marker": 1.0 if re.search(r"\[(?:system|inst)\]|<\|im_start\|>|###\s*instruction", text, re.I) else 0.0,
        "second_person_imperative": min(len(re.findall(r"\byou (?:must|will|are now|should now)\b", text, re.I)), 3) / 3,
        "length": min(len(text), 600) / 600,
    }
