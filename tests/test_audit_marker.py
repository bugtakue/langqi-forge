"""Offline regression for a leading backtick observed in a real final reply.

This checks the completion protocol, not application correctness or GUI coverage.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from factory26_harness.agent import CodingAgent
from factory26_harness.checks import CheckResult
from factory26_harness.trace import ProductionTrace
from factory26_harness.workspace_tools import WorkspaceTools


class AuditMarkerTests(unittest.TestCase):
    def _run_marker(self, marker, *, write=True, valid=True, probe_recheck=False):
        class ScriptedModel:
            turn = 0

            def complete(self, _messages, _schemas):
                self.turn += 1
                if self.turn == 1:
                    name = "write_file" if write else "list_files"
                    arguments = ({"path": "frontend/src/fixture.js",
                                  "content": "export const fixture = true;\n"}
                                 if write else {})
                elif self.turn == 2:
                    name, arguments = "run_validation", {"scope": "quick"}
                else:
                    name, arguments = "", {}
                calls = [{"id": f"fixture-{self.turn}", "type": "function",
                          "function": {"name": name, "arguments": json.dumps(arguments)}}] if name else []
                content = marker if not calls else ""
                return SimpleNamespace(
                    content=content, tool_calls=tuple(calls), finish_reason="stop",
                    raw_message={"role": "assistant", "content": content,
                                 **({"tool_calls": calls} if calls else {})},
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = ProductionTrace(root / ".arc/trace.jsonl")
            tools = WorkspaceTools(root, trace, 33143)
            tools.browser_probe_requires_recheck = probe_recheck
            checks = [CheckResult("fixture", valid, "offline validation", (), 0)]
            with patch("factory26_harness.workspace_tools.run_quick_checks", return_value=checks):
                result = CodingAgent(ScriptedModel(), tools, trace, max_turns=3)._run(
                    "Offline audit-marker fixture", stage="implementation", requirement_ids=[])
            events = [json.loads(line) for line in trace.path.read_text().splitlines()]
            return result, events

    def test_single_backtick_pass_finishes_on_last_turn_without_extra_request(self):
        for marker in ("AUDIT PASS: fixture; GUI unverified",
                       "`AUDIT PASS: fixture; GUI unverified"):
            with self.subTest(marker=marker):
                result, events = self._run_marker(marker)
                self.assertTrue(result.completed)
                self.assertEqual(result.turns, 3)
                self.assertEqual(result.summary, marker)
                self.assertEqual(events[-1]["event"], "agent_session_completed")
                self.assertTrue(events[-1]["payload"]["acceptance_audit_self_reported"])

    def test_single_backtick_blocked_still_stops_as_explicit_failure(self):
        result, events = self._run_marker("`AUDIT BLOCKED: required behavior missing")
        self.assertFalse(result.completed)
        self.assertEqual(events[-1]["event"], "agent_session_stalled")
        self.assertEqual(events[-1]["payload"]["reason"],
                         "model explicitly reported an incomplete requirement")

    def test_marker_does_not_replace_required_source_changes(self):
        result, _ = self._run_marker("`AUDIT PASS: fixture", write=False)
        self.assertFalse(result.completed)

    def test_marker_does_not_replace_passing_validation(self):
        result, _ = self._run_marker("`AUDIT PASS: fixture", valid=False)
        self.assertFalse(result.completed)

    def test_marker_does_not_bypass_required_browser_recheck(self):
        result, _ = self._run_marker("`AUDIT PASS: fixture", probe_recheck=True)
        self.assertFalse(result.completed)

    def test_embedded_quoted_or_lookalike_markers_are_not_accepted(self):
        for marker in ("Example: AUDIT PASS: fixture", '> AUDIT PASS: fixture',
                       '"AUDIT PASS: fixture"', "```AUDIT PASS: fixture",
                       "`AUDIT PASSAGE: fixture", "AUDIT PASSIVE: fixture"):
            with self.subTest(marker=marker):
                result, _ = self._run_marker(marker)
                self.assertFalse(result.completed)


if __name__ == "__main__":
    unittest.main()
