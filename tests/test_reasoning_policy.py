"""Payload-only fixtures. No real model or browser is called."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory26_harness.model import OpenAIChatClient, deepseek_reasoning_options
from factory26_harness.trace import ProductionTrace, verify_trace_rows
from factory26_harness.visual_reference import VisualGatewayConfiguration, VisualReferenceClient
from tests.test_visual_reference import FakeResponse, TINY_PNG


class ReasoningPolicyTests(unittest.TestCase):
    def test_known_coding_models_request_low_effort(self):
        with patch.dict(os.environ, {}, clear=True):
            for model in ("deepseek-flash", "deepseek-v4-flash", "deepseek-v4-pro"):
                self.assertEqual(deepseek_reasoning_options(model), {"reasoning_effort": "low"})

    def test_visual_policy_does_not_disable_coding_reasoning(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(deepseek_reasoning_options("deepseek-v4-flash-vision-exp", visual=True),
                             {"thinking": {"type": "disabled"}})
            self.assertEqual(deepseek_reasoning_options("deepseek-v4-flash-vision-exp"), {})

    def test_unrecognized_models_and_provider_default_are_untouched(self):
        with patch.dict(os.environ, {}, clear=True):
            for model in ("glm-5.3-flash", "fixture-model", "deepseek-unknown"):
                for visual in (False, True):
                    self.assertEqual(deepseek_reasoning_options(model, visual=visual), {})
        with patch.dict(os.environ, {"FACTORY26_DEEPSEEK_REASONING_POLICY": "provider-default"}, clear=True):
            self.assertEqual(deepseek_reasoning_options("deepseek-v4-flash"), {})
            self.assertEqual(deepseek_reasoning_options("deepseek-v4-flash-vision-exp", visual=True), {})

    def test_invalid_policy_fails_locally(self):
        with patch.dict(os.environ, {"FACTORY26_DEEPSEEK_REASONING_POLICY": "typo"}, clear=True):
            with self.assertRaisesRegex(ValueError, "reasoning policy"):
                deepseek_reasoning_options("deepseek-v4-flash")

    def test_coding_request_and_sealed_trace_include_policy_without_changing_caps(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "OPENAI_API_KEY": "fixture-secret", "OPENAI_BASE_URL": "https://gateway.example.test/v1",
            "MODEL": "deepseek-v4-flash",
        }, clear=True):
            trace = ProductionTrace(Path(directory) / "trace.jsonl")
            with patch("factory26_harness.model.urllib.request.urlopen", return_value=FakeResponse()) as request:
                client = OpenAIChatClient(trace)
                client.complete([{"role": "user", "content": "Fixture"}], [])
                payload = json.loads(request.call_args.args[0].data)
            self.assertEqual(payload["reasoning_effort"], "low")
            self.assertNotIn("thinking", payload)
            self.assertEqual(payload["max_tokens"], 8192)
            self.assertEqual(request.call_count, 1)
            rows = [json.loads(line) for line in trace.path.read_text().splitlines()]
            recorded = next(row["payload"]["payload"] for row in rows if row["event"] == "model_request")
            self.assertEqual(recorded["reasoning_effort"], "low")
            self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])

    def test_visual_request_is_single_call_capped_and_auditable(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            (root / "task/reference").mkdir(parents=True)
            (root / "task/reference/home.png").write_bytes(TINY_PNG)
            trace = ProductionTrace(root / "trace.jsonl")
            config = VisualGatewayConfiguration("fixture-secret", "https://gateway.example.test/v1",
                                               "deepseek-v4-flash-vision-exp", "fixture")
            client = VisualReferenceClient(root / "task", trace, config)
            with patch("factory26_harness.visual_reference.urllib.request.urlopen", return_value=FakeResponse()) as request:
                client.describe("reference/home.png")
                payload = json.loads(request.call_args.args[0].data)
                client.describe("reference/home.png")
            self.assertEqual(payload["thinking"], {"type": "disabled"})
            self.assertEqual(payload["max_tokens"], 500)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(client.max_calls, 8)
            rows = [json.loads(line) for line in trace.path.read_text().splitlines()]
            recorded = next(row["payload"] for row in rows if row["event"] == "visual_reference_request")
            self.assertEqual(recorded["requested_reasoning_options"], {"thinking": {"type": "disabled"}})
            self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])


if __name__ == "__main__":
    unittest.main()
