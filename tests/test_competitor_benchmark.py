from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmarks.run_claude_code import (
    CHECKPOINTED_PROMPT_PATH,
    ROOT,
    ensure_fresh_output,
    protocol_violations as claude_protocol_violations,
    requirement_digest,
    resolve_executable,
    trace_metrics,
)
from benchmarks.run_codex import (
    monitor_codex,
    protocol_violations as codex_protocol_violations,
    trace_metrics as codex_trace_metrics,
    validate_codex_version,
)


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
        self.assertIn("--prompt-profile", completed.stdout)

    def test_checkpointed_prompt_forces_early_runnable_state(self) -> None:
        prompt = CHECKPOINTED_PROMPT_PATH.read_text(encoding="utf-8")
        self.assertIn("immediately create both package manifests", prompt)
        self.assertIn("at most two files", prompt)
        self.assertIn("Preserve a runnable state after every increment", prompt)

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

    def test_relative_cli_path_is_resolved_before_workspace_switch(self) -> None:
        with patch(
            "benchmarks.run_claude_code.shutil.which",
            return_value=".cache/benchmark-tools/codex",
        ):
            resolved = resolve_executable(".cache/benchmark-tools/codex")
        self.assertEqual(
            resolved,
            str((ROOT / ".cache/benchmark-tools/codex").resolve()),
        )

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

    def test_codex_protocol_rejects_external_tool_events(self) -> None:
        violation = codex_protocol_violations(
            {
                "type": "item.completed",
                "item": {"type": "mcp_tool_call", "tool": "list_mcp_resources"},
            }
        )
        self.assertTrue(violation)
        self.assertEqual(
            codex_protocol_violations(
                {"type": "item.completed", "item": {"type": "command_execution"}}
            ),
            [],
        )

    def test_codex_version_gate_rejects_incompatible_client(self) -> None:
        self.assertEqual(validate_codex_version("codex-cli 0.151.0"), (0, 151, 0))
        with self.assertRaisesRegex(ValueError, r"0.151.0\+"):
            validate_codex_version("codex-cli 0.137.0")

    def test_codex_monitor_terminates_on_live_protocol_violation(self) -> None:
        fixture = (
            "import json,time; "
            "print(json.dumps({'type':'item.started','item':{'type':'web_search'}}), "
            "flush=True); time.sleep(30)"
        )
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.Popen(
                [sys.executable, "-c", fixture],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                start_new_session=True,
            )
            started = time.monotonic()
            status, returncode, violations = monitor_codex(
                process,
                prompt="",
                trace_path=Path(directory) / "trace.jsonl",
                timeout_seconds=10,
            )
            self.assertEqual(status, "protocol_violation")
            self.assertIsNotNone(returncode)
            self.assertTrue(violations)
            self.assertLess(time.monotonic() - started, 3)

    def test_claude_protocol_rejects_tools_outside_cli_allowlist(self) -> None:
        self.assertEqual(
            claude_protocol_violations(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "tool_use", "name": "Bash"}]},
                }
            ),
            [],
        )
        self.assertEqual(
            claude_protocol_violations(
                {
                    "type": "assistant",
                    "message": {
                        "content": [{"type": "tool_use", "name": "mcp__browser__open"}]
                    },
                }
            ),
            ["forbidden_tool:mcp__browser__open"],
        )


if __name__ == "__main__":
    unittest.main()
