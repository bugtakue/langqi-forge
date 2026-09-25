"""Scripted protocol tests only: no live model or browser is called."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from factory26_harness.agent import CodingAgent
from factory26_harness.checks import CheckResult
from factory26_harness.generic_scaffold import scaffold_workspace
from factory26_harness.requirements import flatten_atomic
from factory26_harness.trace import ProductionTrace
from factory26_harness.workspace_tools import WorkspaceTools


class BrowserBudgetTests(unittest.TestCase):
    def run_case(self, *, outcomes, maximum, edit_after_probe=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold_workspace(root)
            trace = ProductionTrace(root / ".arc/trace.jsonl")
            tools = WorkspaceTools(root, trace, 33345)
            tools.maximum_browser_probe_calls = maximum
            script = [
                ("write_file", {"path": "frontend/src/fixture.js", "content": "export const ok = true;"}),
                ("run_validation", {"scope": "quick"}),
            ] + [("browser_probe", {"steps": [
                {"action": "click", "role": "button", "name": "Save", "expect_text": ["Saved"]}
            ]}) for _ in outcomes]
            if edit_after_probe:
                script.append(("write_file", {"path": "frontend/src/later.js", "content": "export {};"}))
            expected_failure = bool(outcomes) and (not outcomes[-1] or edit_after_probe)
            if not expected_failure:
                script.append("AUDIT PASS: scripted fixture")

            class Model:
                calls = 0

                def complete(self, _messages, _schemas):
                    if self.calls >= len(script):
                        raise AssertionError("unexpected extra model request")
                    item = script[self.calls]
                    self.calls += 1
                    if isinstance(item, str):
                        return SimpleNamespace(tool_calls=(), content=item,
                            raw_message={"role": "assistant", "content": item})
                    name, arguments = item
                    calls = [{"id": str(self.calls), "type": "function", "function": {
                        "name": name, "arguments": json.dumps(arguments)}}]
                    return SimpleNamespace(tool_calls=calls, content="", raw_message={
                        "role": "assistant", "content": "", "tool_calls": calls})

            model = Model()
            with patch("factory26_harness.workspace_tools.run_quick_checks", return_value=[
                CheckResult("fixture", True, "mock validation only", (), 0)
            ]), patch("factory26_harness.workspace_tools.probe_local_app", side_effect=[
                {"ok": outcome, "behavioral_checks": 1, "behavioral_assertions": 1,
                 "assertion_failures": [] if outcome else [{"step": 1, "missing": ["Saved"]}]}
                for outcome in outcomes
            ]) as probe:
                result = CodingAgent(model, tools, trace, max_turns=10).implement(
                    flatten_atomic({"id": "R", "type": "ATOMIC", "name": "Fixture", "description": "Save a record."}))
            self.assertEqual(model.calls, len(script))
            self.assertEqual(probe.call_count, len(outcomes))
            self.assertEqual(result.turns, len(script))
            rows = [json.loads(line) for line in trace.path.read_text().splitlines()]
            if expected_failure:
                self.assertFalse(result.completed)
                self.assertTrue(tools.browser_probe_requires_recheck)
                self.assertEqual(tools.verified_browser_steps, [])
                self.assertIn("budget exhausted", result.summary)
                self.assertTrue(any(row["event"] == "agent_session_stalled" and
                    "budget exhausted" in row["payload"]["reason"] for row in rows))
            else:
                self.assertTrue(result.completed, result.summary)

    def test_failed_last_probe_stops_before_another_model_request(self):
        self.run_case(outcomes=[False], maximum=1)

    def test_last_successful_probe_can_still_complete_audit(self):
        self.run_case(outcomes=[True], maximum=1)

    def test_failure_with_remaining_budget_can_be_rechecked(self):
        self.run_case(outcomes=[False, True], maximum=2)

    def test_edit_after_last_successful_probe_cannot_reuse_old_evidence(self):
        self.run_case(outcomes=[True], maximum=1, edit_after_probe=True)

    def test_explicitly_disabled_probe_does_not_trigger_exhaustion(self):
        self.run_case(outcomes=[], maximum=0)


if __name__ == "__main__":
    unittest.main()
