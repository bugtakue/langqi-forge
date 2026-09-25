import io
import json
import os
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from factory26_harness.model import (
    HTTP_ERROR_BODY_LIMIT, ModelGatewayUnavailable, OpenAIChatClient, _http_error_diagnostics,
)
from factory26_harness.trace import ProductionTrace, verify_trace_rows


class ErrorDiagnosticTests(unittest.TestCase):
    def test_known_message_envelopes_are_classified_without_echoing(self):
        for data, source in (
            ({"error": {"message": "tool_calls mismatch PRIVATE"}}, "error.message"),
            ({"detail": {"message": "tool_calls mismatch PRIVATE"}}, "detail.message"),
            ({"message": "tool_calls mismatch PRIVATE"}, "message"),
            ({"detail": "tool_calls mismatch PRIVATE"}, "detail"),
            ({"error": "tool_calls mismatch PRIVATE"}, "error"),
        ):
            with self.subTest(source=source):
                result = _http_error_diagnostics(json.dumps(data).encode())
                self.assertEqual(result["error_category"], "tool_protocol")
                self.assertEqual(result["error_sources"], [source])
                self.assertEqual(result["error_body_format"], "json_object")
                self.assertNotIn("PRIVATE", json.dumps(result))

    def test_only_exact_known_codes_are_classified(self):
        for path in (("code",), ("type",), ("error", "code"), ("error", "type")):
            for code, expected in (("context_length_exceeded", "context_limit"),
                                   ("context_length_exceeded PRIVATE", "unclassified")):
                data = {path[-1]: code}
                if len(path) == 2:
                    data = {path[0]: data}
                result = _http_error_diagnostics(json.dumps(data).encode())
                self.assertEqual(result["error_category"], expected)
                self.assertEqual(result["error_sources"], [".".join(path)])
                self.assertNotIn("PRIVATE", json.dumps(result))

    def test_conflicting_signals_remain_ambiguous(self):
        result = _http_error_diagnostics(json.dumps({
            "detail": "missing tool_call_id PRIVATE",
            "error": {"code": "context_length_exceeded"},
        }).encode())
        self.assertEqual(result["error_category"], "ambiguous")
        self.assertEqual(result["error_categories"], ["context_limit", "tool_protocol"])
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_unknown_fields_and_values_are_not_logged(self):
        result = _http_error_diagnostics(json.dumps({
            "PRIVATE_FIELD": "reasoning_content PRIVATE_VALUE",
            "detail": {"PRIVATE_FIELD": "tool_calls PRIVATE"},
            "message": ["quota PRIVATE"], "code": "PRIVATE_CODE",
        }).encode())
        self.assertEqual(result["error_category"], "unclassified")
        self.assertEqual(result["error_sources"], ["code"])
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_empty_non_json_non_object_and_deep_json_are_safe(self):
        for body, kind in (
            (b"", "empty"), (b"PRIVATE not JSON", "non_json"),
            (b"\xffPRIVATE", "non_json"), (b'["PRIVATE"]', "other_json"),
            (b'"PRIVATE"', "other_json"),
        ):
            with self.subTest(kind=kind):
                result = _http_error_diagnostics(body)
                self.assertEqual(result["error_category"], "unclassified")
                self.assertEqual(result["error_body_format"], kind)
                self.assertNotIn("PRIVATE", json.dumps(result))
        # CPython versions differ in their native JSON nesting limit; both a
        # safe parse and a caught depth error must remain non-classifying.
        deep = _http_error_diagnostics(b"[" * 2000 + b"0" + b"]" * 2000)
        self.assertEqual(deep["error_category"], "unclassified")
        self.assertIn(deep["error_body_format"], {"non_json", "other_json"})

    def test_truncated_body_is_not_confidently_classified(self):
        for body in (
            b'{"detail":"tool_calls PRIVATE"}' + b" " * HTTP_ERROR_BODY_LIMIT,
            b"x" * (HTTP_ERROR_BODY_LIMIT + 10_000),
        ):
            result = _http_error_diagnostics(body)
            self.assertTrue(result["error_body_truncated"])
            self.assertEqual(result["error_body_bytes_observed"], HTTP_ERROR_BODY_LIMIT + 1)
            self.assertEqual(result["error_body_format"], "truncated")
            self.assertEqual(result["error_category"], "unclassified")
            self.assertEqual(result["error_sources"], [])

    def test_http_boundary_is_bounded_private_and_never_retries_400(self):
        class Body(io.BytesIO):
            sizes = []

            def read(self, size=-1):
                self.sizes.append(size)
                return super().read(size)

        with tempfile.TemporaryDirectory() as directory:
            trace = ProductionTrace(Path(directory) / "trace.jsonl", stdout_progress=True)
            body = Body(b'{"detail":"tool_calls PRIVATE_BODY","PRIVATE_KEY":"PRIVATE_VALUE"}')
            error = urllib.error.HTTPError("https://example.test/v1", 400, "PRIVATE_REASON",
                                          {"retry-after": "1", "private-header": "PRIVATE"}, body)
            output = io.StringIO()
            with patch.dict(os.environ, {"OPENAI_API_KEY": "fixture-key",
                                         "OPENAI_BASE_URL": "https://example.test/v1", "MODEL": "fixture"}), \
                 patch("factory26_harness.model.urllib.request.urlopen", side_effect=error) as send, \
                 patch("factory26_harness.model.time.sleep") as sleep, redirect_stdout(output):
                with self.assertRaisesRegex(ModelGatewayUnavailable, "HTTP 400.*tool_protocol"):
                    OpenAIChatClient(trace).complete([{"role": "user", "content": "fixture"}], [])
            self.assertEqual(send.call_count, 1)
            sleep.assert_not_called()
            self.assertEqual(body.sizes, [HTTP_ERROR_BODY_LIMIT + 1])
            text = trace.path.read_text()
            rows = [json.loads(line) for line in text.splitlines()]
            self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])
            result = rows[-1]["payload"]
            self.assertEqual(result["error_sources"], ["detail"])
            self.assertFalse(result["will_retry"])
            self.assertFalse(result["error_body_truncated"])
            self.assertIn('"error_body_format": "json_object"', output.getvalue())
            self.assertNotIn("PRIVATE", text + output.getvalue())

    def test_body_read_failure_keeps_safe_unknown_diagnostic(self):
        class FailingBody(io.BytesIO):
            def read(self, size=-1):
                raise OSError("PRIVATE read failure")

        with tempfile.TemporaryDirectory() as directory:
            trace = ProductionTrace(Path(directory) / "trace.jsonl")
            error = urllib.error.HTTPError("https://example.test/v1", 400, "PRIVATE", {}, FailingBody())
            with patch.dict(os.environ, {"OPENAI_API_KEY": "fixture-key",
                                         "OPENAI_BASE_URL": "https://example.test/v1", "MODEL": "fixture"}), \
                 patch("factory26_harness.model.urllib.request.urlopen", side_effect=error):
                with self.assertRaisesRegex(ModelGatewayUnavailable, "HTTP 400"):
                    OpenAIChatClient(trace).complete([{"role": "user", "content": "fixture"}], [])
            text = trace.path.read_text()
            result = json.loads(text.splitlines()[-1])["payload"]
            self.assertEqual(result["error_body_format"], "read_failed")
            self.assertEqual(result["error_category"], "unclassified")
            self.assertNotIn("PRIVATE", text)


if __name__ == "__main__":
    unittest.main()
