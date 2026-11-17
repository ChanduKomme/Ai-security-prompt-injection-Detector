# Changelog

## 1.0.0 — 2026-11-17

Complete rewrite as **InjectScope** by Chandu Komme.

- Text normalisation and decoding variants: NFKC, zero-width, homoglyphs, leetspeak, split letters, reversed text, base64.
- 14 explainable intent rules mapped to the OWASP Top 10 for LLM Applications 2025.
- Logistic-regression classifier written from scratch: hashed char/word n-grams, numeric signals, seeded and reproducible.
- Hybrid detector with decoded-payload escalation and an optional LLM judge for the uncertain band.
- Benchmark comparing rules / classifier / hybrid with 5-fold CV and four evaluation sets, including two frozen blind
  sets with SHA-256 checksums; CI gate.
- CLI (`scan`, `train`, `benchmark`, `serve`) and a JSON HTTP API.
- 46 unit tests; GitHub Actions on Python 3.10–3.13.

### Development notes
- First hybrid scored F1 0.63 on `blind`: the classifier copied the rules. Fixed with rule-feature dropout and
  compositional training data, then re-measured on a newly frozen `blind2` (F1 0.95, FPR 0.00).
- Unit tests caught a jailbreak rule firing on "enable developer mode" and missing uppercase Cyrillic homoglyphs.
