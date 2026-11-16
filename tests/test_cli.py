"""End-to-end and CLI reporting tests."""

import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from src.main import main
from src.model_judge import JudgeError


ROOT = Path(__file__).resolve().parents[1]


class TestCLI(unittest.TestCase):
    def test_offline_json_is_one_document(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "src" / "main.py"), "--offline", "--json"],
            cwd=ROOT.parent,
            capture_output=True,
            text=True,
            check=True,
        )
        report = json.loads(result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertEqual(report["model_status"], "offline")
        self.assertIsNone(report["model"])
        self.assertEqual(report["heuristic"]["evaluated"], 30)

    def test_online_setup_failure_is_distinct_from_offline(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(sys, "argv", ["main.py", "--json"]),
            patch("src.main.create_client", side_effect=JudgeError("Missing configuration.")),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(main(), 0)

        report = json.loads(stdout.getvalue())
        self.assertEqual(report["model_status"], "unavailable")
        self.assertIsNone(report["model"])
        self.assertIn("Missing configuration.", stderr.getvalue())
