from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from benchmarks.run_claude_code import (
    ROOT,
    ensure_fresh_output,
    requirement_digest,
    trace_metrics,
)
from benchmarks.run_codex import trace_metrics as codex_trace_metrics


class CompetitorBenchmarkTests(unittest.TestCase):
    def test_codex_runner_direct_script_help_is_executable(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "benchmarks" / "run_codex.py"),
                "--help",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--timeout-seconds", completed.stdout)

    def test_requirement_digest_is_stable_and_content_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            target = root / "nested" / "requirement.txt"
            target.write_text("first", encoding="utf-8")
            first = requirement_digest(root)
            self.assertEqual(first, requirement_digest(root))
            target.write_text("second", encoding="utf-8")
            self.assertNotEqual(first, requirement_digest(root))

    def test_trace_metrics_fail_closed_on_malformed_or_missing_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace.jsonl"
            trace.write_text(
                "not-json\n"
                + json.dumps({"type": "assistant", "message": {}})
                + "\n"
                + json.dumps(
                    {
                        "type": "result",
                        "subtype": "success",
                        "is_error": False,
                        "total_cost_usd": 1.25,
                        "num_turns": 7,
                        "usage": {"input_tokens": 100},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            metrics = trace_metrics(trace)
            self.assertEqual(metrics["event_count"], 3)
            self.assertEqual(metrics["malformed_rows"], 1)
            self.assertEqual(metrics["total_cost_usd"], 1.25)
            self.assertEqual(metrics["num_turns"], 7)
            self.assertEqual(metrics["duration_api_ms"], "unknown")
            self.assertIs(metrics["is_error"], False)
            self.assertEqual(metrics["api_error_status"], "unknown")

    def test_output_must_be_new_or_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            self.assertEqual(ensure_fresh_output(root), root.resolve())
            (root / "existing.txt").write_text("preserve", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must not exist or must be empty"):
                ensure_fresh_output(root)
            self.assertEqual((root / "existing.txt").read_text(), "preserve")

    def test_codex_trace_metrics_retain_terminal_usage_and_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "codex.jsonl"
            trace.write_text(
                "not-json\n"
                + json.dumps({"type": "thread.started", "thread_id": "thread-1"})
                + "\n"
                + json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {"input_tokens": 20, "output_tokens": 5},
                    }
                )
                + "\n"
                + json.dumps({"type": "error", "message": "fixture failure"})
                + "\n",
                encoding="utf-8",
            )
            metrics = codex_trace_metrics(trace)
            self.assertEqual(metrics["malformed_rows"], 1)
            self.assertEqual(metrics["thread_id"], "thread-1")
            self.assertEqual(metrics["usage"]["input_tokens"], 20)
            self.assertEqual(metrics["terminal_error"], "fixture failure")


if __name__ == "__main__":
    unittest.main()
