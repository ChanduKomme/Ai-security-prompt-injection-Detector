"""Small JSON HTTP API (standard library only).

Author: Chandu Komme

Endpoints
---------
GET  /health          -> {"status": "ok", "version": ...}
POST /scan            {"text": "..."}            -> scan result
POST /scan/batch      {"texts": ["...", ...]}    -> {"results": [...]}  (max 100)

Bodies over 64 KiB are rejected, and so are texts over 20,000 characters.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .detector import Detector

__author__ = "Chandu Komme"

MAX_BODY = 64 * 1024
MAX_TEXT = 20_000
MAX_BATCH = 100


def make_handler(detector: Detector):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"InjectScope/{__version__}"

        def log_message(self, fmt, *args):  # keep test output quiet
            pass

        def _send(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self._send(200, {"status": "ok", "version": __version__, "mode": detector.mode,
                                 "threshold": detector.threshold, "judge": detector.judge is not None})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                return self._send(413 if length > MAX_BODY else 400, {"error": "body must be 1 byte to 64 KiB"})
            try:
                data = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return self._send(400, {"error": "invalid JSON"})
            if not isinstance(data, dict):
                return self._send(400, {"error": "expected a JSON object"})

            if self.path == "/scan":
                text = data.get("text")
                if not isinstance(text, str) or not text or len(text) > MAX_TEXT:
                    return self._send(400, {"error": f"'text' must be a non-empty string up to {MAX_TEXT} chars"})
                return self._send(200, detector.scan(text).to_dict())

            if self.path == "/scan/batch":
                texts = data.get("texts")
                if (not isinstance(texts, list) or not texts or len(texts) > MAX_BATCH
                        or not all(isinstance(t, str) and t and len(t) <= MAX_TEXT for t in texts)):
                    return self._send(400, {"error": f"'texts' must be 1-{MAX_BATCH} non-empty strings"})
                return self._send(200, {"results": [detector.scan(t).to_dict() for t in texts]})

            self._send(404, {"error": "not found"})

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8088, detector: Detector | None = None) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(detector or Detector()))
