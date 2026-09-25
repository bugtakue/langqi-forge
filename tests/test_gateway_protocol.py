import json
import io
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from factory26_harness.agent import _assistant_message, _fresh_observation_messages
from factory26_harness.model import OpenAIChatClient, ModelGatewayUnavailable, _http_error_category
from factory26_harness.trace import ProductionTrace


class GatewayProtocolTests(unittest.TestCase):
    def test_replay_provider_reasoning_without_unknown_metadata(self):
        for calls in ([], [{"id": "read", "function": {"name": "read_file"}}]):
            raw = {"content": "", "reasoning_content": "opaque provider continuation",
                   "tool_calls": calls, "unknown": "do not propagate"}
            replay = _assistant_message(raw)
            self.assertEqual(replay["reasoning_content"], raw["reasoning_content"])
            self.assertNotIn("unknown", replay)
        self.assertNotIn("reasoning_content", _assistant_message({"content": "ordinary"}))

    def test_compaction_retains_protocol_field_and_matching_read_results(self):
        messages = [
            {"role": "assistant", "content": "", "reasoning_content": "opaque continuation",
             "tool_calls": [{"id": "read", "function": {"name": "read_file"}},
                            {"id": "write", "function": {"name": "write_file"}}]},
            {"role": "tool", "tool_call_id": "read", "content": "observed"},
            {"role": "tool", "tool_call_id": "write", "content": "written"},
        ]
        retained = _fresh_observation_messages(messages)
        self.assertEqual(retained[0]["reasoning_content"], "opaque continuation")
        self.assertEqual([c["id"] for c in retained[0]["tool_calls"]], ["read"])
        self.assertEqual(retained[1], messages[1])
        self.assertEqual(len(retained), 2)

    def test_error_classification_never_returns_provider_text(self):
        cases = [
            ("reasoning_content is missing secret=PRIVATE", "reasoning_protocol"),
            ("tool_calls must match tool_call_id PRIVATE", "tool_protocol"),
            ("maximum context length exceeded PRIVATE", "context_limit"),
            ("unsupported parameter PRIVATE", "unsupported_parameter"),
            ("insufficient quota PRIVATE", "quota_or_capacity"),
            ("PRIVATE", "unclassified"),
        ]
        for message, expected in cases:
            self.assertEqual(_http_error_category(json.dumps({"error": {"message": message}}).encode()), expected)
        self.assertEqual(_http_error_category(b'PRIVATE invalid JSON'), "unclassified")
        self.assertEqual(_http_error_category(b'{"error": "PRIVATE"}'), "unclassified")

    def test_http_400_keeps_only_category_and_never_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = ProductionTrace(Path(directory) / "trace.jsonl")
            body = json.dumps({"error": {"message": "Missing reasoning_content PRIVATE_BODY"}}).encode()
            error = urllib.error.HTTPError("https://example.test/v1", 400, "bad request", {}, io.BytesIO(body))
            with patch.dict(os.environ, {"OPENAI_API_KEY": "fixture-key",
                                         "OPENAI_BASE_URL": "https://example.test/v1", "MODEL": "fixture"}), \
                 patch("factory26_harness.model.urllib.request.urlopen", side_effect=error) as send:
                client = OpenAIChatClient(trace)
                with self.assertRaisesRegex(ModelGatewayUnavailable, "HTTP 400.*reasoning_protocol"):
                    client.complete([{"role": "user", "content": "small fixture"}], [])
            self.assertEqual(send.call_count, 1)
            rows = [json.loads(line) for line in trace.path.read_text().splitlines()]
            self.assertEqual(rows[-1]["payload"]["error_category"], "reasoning_protocol")
            self.assertNotIn("PRIVATE_BODY", trace.path.read_text())
