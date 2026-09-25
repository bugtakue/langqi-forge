import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory26_harness.trace import ProductionTrace, verify_trace_rows


class ProgressTraceTests(unittest.TestCase):
    def test_console_has_failures_but_not_prompts_sources_or_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            trace = ProductionTrace(path, stdout_progress=True)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                trace.record("model_request", messages="PRIVATE_PROMPT")
                trace.record("tool_call", arguments={"content": "PRIVATE_SOURCE"})
                trace.record("tool_result", tool="read_file", result={
                    "ok": True, "path": "frontend/src/app.js", "content": "PRIVATE_SOURCE",
                })
                trace.record("tool_result", tool="write_file", result={
                    "ok": False, "error": "invalid API_KEY=sk-testcredential123456789",
                })
                trace.record("implementation_batch_finished", batch=1, completed=False,
                             summary="maximum tool turns reached", turns=20)
            rendered = output.getvalue()
            self.assertNotIn("PRIVATE_", rendered)
            self.assertNotIn("sk-test", rendered)
            self.assertIn("[REDACTED]", rendered)
            self.assertIn("maximum tool turns reached", rendered)
            self.assertIn('"completed": false', rendered)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])

    def test_progress_is_opt_in_bounded_and_single_line(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            trace = ProductionTrace(Path(directory) / "trace.jsonl")
            with contextlib.redirect_stdout(output):
                trace.record("run_failed", error="silent")
            self.assertEqual(output.getvalue(), "")
            trace.stdout_progress = True
            with contextlib.redirect_stdout(output):
                trace.record("run_failed", error="line\n" * 4000)
            self.assertEqual(len(output.getvalue().splitlines()), 1)
            self.assertLess(len(output.getvalue()), 2000)

    def test_broken_console_does_not_lose_trace_or_raise(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            trace = ProductionTrace(path, stdout_progress=True)
            with patch("builtins.print", side_effect=BrokenPipeError):
                trace.record("run_failed", error="failure evidence")
            self.assertFalse(trace.stdout_progress)
            self.assertIn("failure evidence", path.read_text())
