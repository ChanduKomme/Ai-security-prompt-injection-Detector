"""Hand-written regex/heuristic prompt-injection scanner.

No framework, no model call. Four detector families, each returning the matched pattern
name(s) so a caller can see *why* something was flagged, not just a boolean.

This is deliberately the "aid, not a control" half of the project — see the README for why
a heuristic-only gate is not a substitute for output validation and privilege limits.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field

# --- Family 1: instruction-override framing -------------------------------------------
_OVERRIDE_PATTERNS = [
    re.compile(r"\bignore\s+(all\s+)?(the\s+)?previous\s+instructions\b", re.I),
    re.compile(r"\bignore\s+(all\s+)?(the\s+)?(above|prior)\b", re.I),
    re.compile(r"\bdisregard\s+(all\s+)?(the\s+)?(previous|prior|above)\b", re.I),
    re.compile(r"\bforget\s+(everything|all)\s+(you\s+)?(were\s+told|above)\b", re.I),
    re.compile(r"\byour\s+new\s+instructions\s+are\b", re.I),
    re.compile(r"\boverride\s+(your\s+)?(system\s+)?prompt\b", re.I),
]

# --- Family 2: role-play jailbreak framing --------------------------------------------
_ROLEPLAY_PATTERNS = [
    re.compile(r"\byou\s+are\s+now\s+(dan|dev\s?mode|jailbroken|unfiltered|unrestricted)\b", re.I),
    re.compile(r"\bact\s+as\s+(an?\s+)?(ai\s+)?with\s+no\s+(restrictions|rules|filters)\b", re.I),
    re.compile(r"\bpretend\s+(you\s+have\s+)?no\s+(content\s+)?polic(y|ies)\b", re.I),
    re.compile(r"\benable\s+developer\s+mode\b", re.I),
    re.compile(r"\bin\s+this\s+hypothetical\s+scenario.{0,40}\bno\s+rules\b", re.I),
]

# --- Family 3: fake system/boundary injection -----------------------------------------
_BOUNDARY_PATTERNS = [
    re.compile(r"^\s*system\s*:\s*", re.I | re.M),
    re.compile(r"\[/?(system|inst)\]", re.I),
    re.compile(r"<\|?(system|im_start|im_end)\|?>", re.I),
    re.compile(r"</?(system_prompt|untrusted_input|end_of_context)>", re.I),
    re.compile(r"---\s*end\s+of\s+(user\s+)?(input|message)\s*---", re.I),
]

# --- Family 4: encoded / obfuscated payloads -------------------------------------------
_B64_CANDIDATE = re.compile(r"\b[A-Za-z0-9+/]{24,}={0,2}\b")
_HEX_CANDIDATE = re.compile(r"\b(?:[0-9a-fA-F]{2}){12,}\b")
_DECODED_RED_FLAGS = re.compile(
    r"ignore|disregard|system prompt|jailbreak|no restrictions|override", re.I
)


def _try_decode_base64(token: str) -> str | None:
    padded = token + "=" * (-len(token) % 4)
    try:
        decoded = base64.b64decode(padded, validate=True).decode("utf-8", errors="strict")
    except Exception:
        return None
    return decoded if decoded.isprintable() else None


def _try_decode_hex(token: str) -> str | None:
    try:
        decoded = bytes.fromhex(token).decode("utf-8", errors="strict")
    except Exception:
        return None
    return decoded if decoded.isprintable() else None


@dataclass
class HeuristicResult:
    is_flagged: bool
    matched_patterns: list[str] = field(default_factory=list)
    decoded_payload: str | None = None

    def to_dict(self) -> dict:
        return {
            "is_flagged": self.is_flagged,
            "matched_patterns": self.matched_patterns,
            "decoded_payload": self.decoded_payload,
        }


def scan(text: str) -> HeuristicResult:
    matched: list[str] = []
    decoded_payload: str | None = None

    for pat in _OVERRIDE_PATTERNS:
        if pat.search(text):
            matched.append(f"override:{pat.pattern[:40]}")
    for pat in _ROLEPLAY_PATTERNS:
        if pat.search(text):
            matched.append(f"roleplay:{pat.pattern[:40]}")
    for pat in _BOUNDARY_PATTERNS:
        if pat.search(text):
            matched.append(f"boundary:{pat.pattern[:40]}")

    for token in _B64_CANDIDATE.findall(text):
        decoded = _try_decode_base64(token)
        if decoded and _DECODED_RED_FLAGS.search(decoded):
            matched.append("encoded:base64")
            decoded_payload = decoded
            break
    if decoded_payload is None:
        for token in _HEX_CANDIDATE.findall(text):
            decoded = _try_decode_hex(token)
            if decoded and _DECODED_RED_FLAGS.search(decoded):
                matched.append("encoded:hex")
                decoded_payload = decoded
                break

    return HeuristicResult(is_flagged=bool(matched), matched_patterns=matched, decoded_payload=decoded_payload)
