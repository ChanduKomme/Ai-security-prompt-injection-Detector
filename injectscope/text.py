"""Text canonicalization used by both the rules and the classifier.

Author: Chandu Komme

``canonical`` produces one comparable form of a prompt: Unicode NFKC,
invisible characters dropped, Cyrillic and Greek look-alikes mapped to Latin,
lowercase, and collapsed whitespace. ``variants`` adds the forms attackers use
to hide words: leetspeak undone, single-letter spacing or hyphenation joined,
reversed text, and readable base64 payloads decoded.
"""

from __future__ import annotations

import base64
import binascii
import math
import re
import unicodedata
from collections import Counter

__author__ = "Chandu Komme"

_INVISIBLE = {ord(c): None for c in "​‌‍‎‏⁠⁦⁧⁨⁩﻿­"}
_LOOKALIKE = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s",
    "ԁ": "d", "һ": "h", "ӏ": "l", "ս": "u", "ν": "v", "ο": "o", "α": "a", "ε": "e", "ι": "i", "τ": "t",
    "υ": "u", "ρ": "p", "χ": "x", "А": "a", "Е": "e", "О": "o", "Р": "p", "С": "c", "Х": "x", "І": "i", "Ѕ": "s",
    "Т": "t", "Н": "h", "М": "m", "К": "k", "В": "b", "Υ": "y", "Ν": "n", "Κ": "k", "Μ": "m", "Τ": "t",
})
_LEET = str.maketrans("013457@$", "oieastas")
_WS = re.compile(r"\s+")
_SYMBOL_SPLIT = re.compile(r"(?<![a-z])(?:[a-z][\-.*_]){2,}[a-z](?![a-z])")
_SPACE_SPLIT = re.compile(r"(?<![a-z])(?:[a-z] ){3,}[a-z](?![a-z])")
_B64 = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")


def canonical(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_INVISIBLE).translate(_LOOKALIKE)
    return _WS.sub(" ", text.lower()).strip()


def decoded_payloads(text: str) -> list[str]:
    out = []
    for token in _B64.findall(text):
        try:
            raw = base64.b64decode(token + "=" * (-len(token) % 4), validate=True).decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            continue
        if sum(ch.isalpha() or ch == " " for ch in raw) >= 0.85 * len(raw) and len(raw) >= 12:
            out.append(canonical(raw))
    return out


def variants(text: str) -> list[tuple[str, str]]:
    base = canonical(text)
    forms = [("canonical", base)]
    unleet = base.translate(_LEET)
    if unleet != base:
        forms.append(("leetspeak", unleet))
    joined = _SYMBOL_SPLIT.sub(lambda m: re.sub(r"[\-.*_]", "", m.group(0)), base)
    raw = unicodedata.normalize("NFKC", text).translate(_INVISIBLE).lower().strip()
    if re.search(r"\S {2,}\S", raw) and _SPACE_SPLIT.search(raw):
        # "i g n o r e   a l l" : letters split by one space, words by several
        chunks = re.split(r" {2,}", raw)
        joined = " ".join(c.replace(" ", "") if re.fullmatch(r"(?:\S )+\S", c) else c for c in chunks)
        joined = _WS.sub(" ", joined.translate(_LOOKALIKE))
    joined = _SPACE_SPLIT.sub(lambda m: m.group(0).replace(" ", ""), joined)
    if joined != base:
        forms.append(("split_letters", joined))
    forms.append(("reversed", base[::-1]))
    forms += [("base64", p) for p in decoded_payloads(text)]
    return forms


def entropy(token: str) -> float:
    if not token:
        return 0.0
    counts = Counter(token)
    return -sum(n / len(token) * math.log2(n / len(token)) for n in counts.values())


def script_mix(text: str) -> float:
    """Share of letters that are Cyrillic or Greek inside mostly Latin text (homoglyph signal)."""
    letters = [c for c in unicodedata.normalize("NFKC", text) if c.isalpha()]
    if not letters:
        return 0.0
    foreign = sum(1 for c in letters if "CYRILLIC" in unicodedata.name(c, "") or "GREEK" in unicodedata.name(c, ""))
    latin = sum(1 for c in letters if "LATIN" in unicodedata.name(c, ""))
    return foreign / len(letters) if latin and foreign else 0.0
