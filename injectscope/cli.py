"""Command-line interface.

Author: Chandu Komme

    injectscope scan "text"            # one input, human-readable
    injectscope scan --json "text"     # machine-readable
    injectscope scan --file inputs.txt # one input per line (or .jsonl with a "text" field)
    injectscope train                  # retrain both models from data/train.jsonl
    injectscope benchmark              # full evaluation + gate (exit 1 if it fails)
    injectscope serve --port 8088      # JSON HTTP API

Exit codes for ``scan``: 0 = all benign, 2 = at least one attack, 1 = usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .detector import Detector
from .judge import AnthropicJudge

__author__ = "Chandu Komme"

RED, GREEN, DIM, RESET = "\033[31m", "\033[32m", "\033[2m", "\033[0m"


def _color(enabled: bool):
    return (lambda code, s: f"{code}{s}{RESET}") if enabled else (lambda code, s: s)


def _read_inputs(path: str) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    if path.endswith(".jsonl"):
        return [json.loads(line)["text"] for line in lines if line.strip()]
    return [line for line in lines if line.strip()]


def _print_result(text: str, res, paint) -> None:
    tag = paint(RED, "ATTACK") if res.is_attack else paint(GREEN, "benign")
    print(f"{tag}  score={res.score:.3f}  threshold={res.threshold}  mode={res.mode}  ({res.latency_ms} ms)")
    print(paint(DIM, f"  input: {text[:100]}{'...' if len(text) > 100 else ''}"))
    for hit in res.rules:
        print(f"  rule {hit['id']} [{hit['owasp']}/{hit['family']}] via {hit['variant']}: {hit['why']}")
        print(paint(DIM, f"       matched: {hit['evidence']}"))
    if res.top_features:
        feats = ", ".join(f"{f['feature']}({f['contribution']:+.2f})" for f in res.top_features[:4])
        print(paint(DIM, f"  model: {feats}"))
    if res.judge:
        print(f"  judge: attack={res.judge['attack']} confidence={res.judge['confidence']} - {res.judge['reason']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="injectscope", description="Hybrid prompt-injection detector")
    parser.add_argument("--version", action="version", version=f"injectscope {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="scan text for prompt injection")
    scan.add_argument("text", nargs="?", help="text to scan (or use --file / stdin)")
    scan.add_argument("--file", help="file with one input per line, or .jsonl with a 'text' field")
    scan.add_argument("--mode", choices=Detector.MODES, default="hybrid")
    scan.add_argument("--threshold", type=float)
    scan.add_argument("--judge", action="store_true", help="use the LLM judge for uncertain cases (needs ANTHROPIC_API_KEY)")
    scan.add_argument("--json", action="store_true")

    sub.add_parser("train", help="retrain the models")
    sub.add_parser("benchmark", help="run the benchmark and gate")
    serve_p = sub.add_parser("serve", help="run the HTTP API")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8088)
    serve_p.add_argument("--judge", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "train":
        from .train import train
        print(json.dumps(train(), indent=2))
        return 0
    if args.command == "benchmark":
        from .benchmark import markdown, run
        report = run()
        print(markdown(report))
        return 0 if report["gate"]["passed"] else 1

    judge = None
    if getattr(args, "judge", False):
        judge = AnthropicJudge.from_env()
        if judge is None:
            print("--judge needs ANTHROPIC_API_KEY; continuing without it", file=sys.stderr)

    if args.command == "serve":
        from .server import serve
        server = serve(args.host, args.port, Detector(judge=judge))
        print(f"InjectScope {__version__} listening on http://{args.host}:{args.port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        return 0

    detector = Detector(args.mode, threshold=args.threshold, judge=judge)
    if args.file:
        texts = _read_inputs(args.file)
    elif args.text:
        texts = [args.text]
    elif not sys.stdin.isatty():
        texts = [sys.stdin.read().strip()]
    else:
        parser.error("give text, --file or pipe input on stdin")
        return 1

    results = [detector.scan(t) for t in texts if t]
    if args.json:
        payload = [r.to_dict() for r in results]
        print(json.dumps(payload[0] if len(payload) == 1 else payload, indent=2, ensure_ascii=False))
    else:
        paint = _color(sys.stdout.isatty())
        for text, res in zip(texts, results):
            _print_result(text, res, paint)
        if len(results) > 1:
            flagged = sum(r.is_attack for r in results)
            print(f"\n{flagged}/{len(results)} flagged as attacks")
    return 2 if any(r.is_attack for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
