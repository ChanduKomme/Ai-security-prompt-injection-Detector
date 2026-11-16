"""Claude contract tests using local stubs."""

import os
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from src.main import score_model
from src.model_judge import ENV_FILE, JudgeError, create_client, judge


BENIGN_INPUT = "Summarize the meeting notes."
BENIGN_VERDICT = {"is_injection": False, "confidence": "high", "rationale": "Routine request."}


def response(*payloads, stop_reason="tool_use"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[
            SimpleNamespace(type="tool_use", name="report_verdict", input=payload)
            for payload in payloads
        ],
    )


def client_for(*replies):
    return SimpleNamespace(messages=SimpleNamespace(create=Mock(side_effect=replies)))


class TestJudge(unittest.TestCase):
    def test_accepts_a_single_typed_verdict(self):
        client = client_for(response(BENIGN_VERDICT))
        self.assertEqual(judge(BENIGN_INPUT, client=client), BENIGN_VERDICT)
        request = client.messages.create.call_args.kwargs
        self.assertTrue(request["tools"][0]["strict"])
        self.assertEqual(request["tool_choice"]["type"], "auto")

    def test_rejects_incomplete_or_malformed_verdicts(self):
        invalid_responses = {
            "missing tool call": response(stop_reason="end_turn"),
            "duplicate tool call": response(BENIGN_VERDICT, BENIGN_VERDICT),
            "missing boolean": response({"confidence": "high", "rationale": "Routine request."}),
            "string boolean": response({**BENIGN_VERDICT, "is_injection": "false"}),
            "truncated response": response(BENIGN_VERDICT, stop_reason="max_tokens"),
            "oversize rationale": response({**BENIGN_VERDICT, "rationale": "x" * 301}),
        }
        for name, reply in invalid_responses.items():
            with self.subTest(name=name):
                with self.assertRaises(JudgeError):
                    judge(BENIGN_INPUT, client=client_for(reply))

    def test_unscored_row_keeps_other_model_results(self):
        client = client_for(
            response(BENIGN_VERDICT),
            TimeoutError("simulated timeout"),
            response(BENIGN_VERDICT),
        )
        dataset = [
            {"id": f"b{number}", "label": "benign", "text": BENIGN_INPUT}
            for number in range(3)
        ]
        result = score_model(dataset, client=client)
        self.assertEqual(result["evaluated"], 2)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["tn"], 2)
        self.assertIsNone(result["rows"][1]["model_flagged"])
        self.assertIn("TimeoutError", result["rows"][1]["error"])

    def test_loads_project_dotenv_before_configuring_client(self):
        client = client_for(response(BENIGN_VERDICT))
        provider = ModuleType("anthropic")
        provider.Anthropic = Mock(return_value=client)
        dotenv = ModuleType("dotenv")

        def load_fixture_config(*args, **kwargs):
            os.environ["ANTHROPIC_API_KEY"] = "offline-test-value"
            os.environ["ANTHROPIC_MODEL"] = "offline-test-model"

        dotenv.load_dotenv = Mock(side_effect=load_fixture_config)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.dict(sys.modules, {"anthropic": provider, "dotenv": dotenv}),
        ):
            configured_client = create_client()
            self.assertIs(configured_client, client)
            judge(BENIGN_INPUT, client=configured_client)

        dotenv.load_dotenv.assert_called_once_with(ENV_FILE, override=False)
        self.assertEqual(client.messages.create.call_args.kwargs["model"], "offline-test-model")
