# Prompt Injection Detector

A Python benchmark for learning how to detect prompt injection and measure classification errors. It compares an explainable local scanner with an optional Claude judge on the same 30 labeled examples.

## Run locally

Use **Python 3.10 or newer**. From the repository root, run the scanner and tests with the standard library.

```bash
python3 src/main.py --offline
python3 -m unittest discover -s tests -t .
```

Use `--json` to save a machine-readable report. Standard output contains one JSON document. Diagnostics go to standard error.

```bash
python3 src/main.py --offline --json > report.json
python3 -m json.tool report.json
```

## What the detector checks

| Signal | What the scanner looks for |
| --- | --- |
| Instruction overrides | Phrases that ask the model to replace or disregard instructions |
| Role-play framing | Known wording that asks the model to act without its usual constraints |
| Fake message boundaries | Text that resembles a new system message or context delimiter |
| Encoded text | Printable Base64 or hex decodes that contain recognized phrases |

Each flagged row includes its matching rules. The evaluator compares the flag with the fixture label and reports precision, recall, and the four confusion-matrix counts.

| Method | Precision | Recall | True positives | False positives | False negatives | True negatives |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Local scanner | 100% | 93.3% | 14 | 0 | 1 | 15 |

Precision measures how many flagged prompts have an injection label. Recall measures how many prompts with an injection label were flagged. These results describe the bundled benchmark. Use a separate set of representative examples to estimate performance on other inputs.

## Optional Claude comparison

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Set `ANTHROPIC_API_KEY` in `.env` or your process environment, then run `python3 src/main.py`. The program loads `.env` from the repository root, and exported variables take precedence. `ANTHROPIC_MODEL` selects the model and defaults to `claude-opus-5`. The project ignores `.env` in Git.

The optional comparison sends each fixture’s original text to Anthropic. Claude receives a strict schema for the verdict. The evaluator verifies the returned boolean, confidence label, and rationale before scoring each row. A request failure or invalid verdict produces an unscored row and the batch continues.

| `model_status` | Meaning |
| --- | --- |
| `offline` | The local-only mode was selected. |
| `complete` | Claude returned a valid verdict for every row. |
| `partial` | Some rows received valid verdicts. Scores cover those rows. |
| `unavailable` | Online setup failed or zero rows received valid verdicts. |

In JSON, an unscored row has `model_flagged: null` and an `error`. The `evaluated` and `total` counts show coverage. The confidence label is self-reported by Claude.

## Project files

| Path | Purpose |
| --- | --- |
| [`src/heuristics.py`](src/heuristics.py) | Local detection rules and matched-rule explanations |
| [`src/model_judge.py`](src/model_judge.py) | Claude configuration, request, and verdict validation |
| [`src/main.py`](src/main.py) | Dataset loading, metric calculation, and CLI reports |
| [`data/labeled_prompts.json`](data/labeled_prompts.json) | Thirty labeled benchmark fixtures |
| [`tests/`](tests/) | Scanner, scoring, CLI, and mocked Claude regression tests |

## Security scope

Use the verdicts as triage signals. An application that handles private data or takes actions should enforce access control and validate actions independently of the classifier.

## Attribution

Adapted from Sanjeev Jaiswal’s [Prompt-Injection Detector](https://github.com/jassics/ai-security-projects/tree/3ea65ff7a4bf1d8c74f54e4271ab36275c015bdc/01-prompt-injection-detector). This version adds validated model verdicts, per-row failure reporting, clean JSON output, and regression tests. The original copyright notice is included in the [MIT license](LICENSE).
