"""Offline completion-boundary fixtures, never a live model or browser."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from factory26_harness.agent import CodingAgent, _completion_tail_enabled, _tail_probe_arguments
from factory26_harness.checks import CheckResult
from factory26_harness.generic_scaffold import scaffold_workspace
from factory26_harness.model import ModelBudgetExceeded
from factory26_harness.requirements import flatten_atomic
from factory26_harness.trace import ProductionTrace, verify_trace_rows
from factory26_harness.workspace_tools import WorkspaceTools


FLOW = [{"action": "click", "role": "button", "name": "Save", "expect_text": ["Saved"]}]


def reply(item, index):
    if isinstance(item, str):
        return SimpleNamespace(content=item, tool_calls=[], finish_reason="stop",
                               raw_message={"content": item})
    name, arguments = item
    calls = [{"id": f"call-{index}", "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments)}}]
    return SimpleNamespace(content="", tool_calls=calls, finish_reason="tool_calls",
                           raw_message={"content": "", "reasoning_content": "opaque fixture field",
                                        "tool_calls": calls})


class CompletionTailTests(unittest.TestCase):
    def run_boundary(self, *, enabled=True, tail=None, probe_outcome=True, inspection=False,
                     budget_at=None, mutate_at_audit=False, audit_only=False):
        tail = tail if tail is not None else [
            ("browser_probe", {"steps": [] if inspection else FLOW}), "AUDIT PASS: fixture",
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold_workspace(root)
            trace = ProductionTrace(root / "trace.jsonl")
            tools = WorkspaceTools(root, trace, 19449)
            script = [
                ("write_file", {"path": "frontend/src/first.js", "content": "export const a = 1;"}),
                ("run_validation", {"scope": "quick"}),
                ("browser_probe", {"steps": FLOW}),
                ("write_file", {"path": "frontend/src/repair.js", "content": "export const b = 2;"}),
                ("run_validation", {"scope": "quick"}),
            ] + tail
            if audit_only:
                script = script[:3] + [("list_files", {}), ("list_files", {}), "AUDIT PASS: fixture"]

            class Model:
                def __init__(self):
                    self.requests = []

                def complete(self, messages, schemas):
                    self.requests.append(json.loads(json.dumps({"messages": messages, "schemas": schemas})))
                    index = len(self.requests)
                    if budget_at == index:
                        raise ModelBudgetExceeded("fixture global token cap")
                    if mutate_at_audit and index == 7:
                        tools.change_revision += 1
                    return reply(script[index - 1], index)

            model = Model()
            outcome = {"ok": probe_outcome, "behavioral_checks": 0 if inspection else 1,
                       "behavioral_assertions": 0 if inspection else 1}
            with patch.dict(os.environ, {"FACTORY26_COMPLETION_TAIL": "1" if enabled else "0"}), \
                 patch("factory26_harness.workspace_tools.run_quick_checks", return_value=[
                     CheckResult("fixture", True, "mock only", (), 0)]), \
                 patch("factory26_harness.workspace_tools.probe_local_app", side_effect=[
                     {"ok": audit_only, "behavioral_checks": 1, "behavioral_assertions": 1}, outcome]) as probe:
                agent = CodingAgent(model, tools, trace, max_turns=5)
                if audit_only:
                    tools.maximum_browser_probe_calls = 1
                    agent.maximum_total_tool_calls = 5
                if budget_at:
                    with self.assertRaisesRegex(ModelBudgetExceeded, "global token cap"):
                        agent.implement(flatten_atomic({"id": "R", "type": "ATOMIC", "name": "Fixture",
                                                       "description": "Save a record and verify it."}))
                    self.assertEqual(len(model.requests), budget_at)
                    return
                result = agent.implement(flatten_atomic({"id": "R", "type": "ATOMIC", "name": "Fixture",
                                                        "description": "Save a record and verify it."}))
            rows = [json.loads(x) for x in trace.path.read_text().splitlines()]
            self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])
            self.assertEqual(tools.write_operations, 1 if audit_only else 2)
            return result, model.requests, probe.call_count, rows

    def test_default_off_preserves_exhaustion_and_never_spends_tail_calls(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(_completion_tail_enabled())
        result, requests, probes, _ = self.run_boundary(enabled=False)
        self.assertFalse(result.completed)
        self.assertEqual((result.turns, len(requests), probes), (5, 5, 1))

    def test_validated_last_turn_can_reprobe_then_audit_without_more_writes(self):
        result, requests, probes, rows = self.run_boundary()
        self.assertTrue(result.completed, result.summary)
        started = next(row for row in rows if row["event"] == "agent_session_started")
        self.assertIs(started["payload"]["completion_tail_enabled"], True)
        self.assertEqual((result.turns, len(requests), probes), (7, 7, 2))
        self.assertEqual([x["function"]["name"] for x in requests[5]["schemas"]], ["browser_probe"])
        self.assertEqual(requests[6]["schemas"], [])
        prior = next(m for m in requests[6]["messages"] if m.get("tool_calls", [{}])[0].get("id") == "call-6")
        self.assertEqual(prior["reasoning_content"], "opaque fixture field")
        self.assertTrue(any(m.get("tool_call_id") == "call-6" for m in requests[6]["messages"]))
        self.assertEqual(len([r for r in rows if r["event"] == "agent_completion_tail_started"]), 1)

    def test_tail_forbids_writes_even_if_model_ignores_advertised_tools(self):
        result, requests, probes, _ = self.run_boundary(tail=[
            ("write_file", {"path": "frontend/src/forbidden.js", "content": "export {};"})])
        self.assertFalse(result.completed)
        self.assertEqual((len(requests), probes), (6, 1))

    def test_verified_revision_needs_only_audit_even_with_no_tool_budget_left(self):
        result, requests, probes, _ = self.run_boundary(audit_only=True)
        self.assertTrue(result.completed, result.summary)
        self.assertEqual((result.turns, len(requests), probes), (6, 6, 1))
        self.assertEqual(requests[-1]["schemas"], [])

    def test_failed_or_inspection_only_probe_cannot_reach_audit(self):
        for options in ({"probe_outcome": False}, {"inspection": True}):
            with self.subTest(options=options):
                result, requests, probes, _ = self.run_boundary(**options)
                self.assertFalse(result.completed)
                self.assertEqual((len(requests), probes), (6, 2))

    def test_global_model_budget_exception_is_not_retried_or_swallowed(self):
        for index in (6, 7):
            with self.subTest(index=index):
                self.run_boundary(budget_at=index)

    def test_audit_cannot_execute_tools_or_accept_missing_evidence(self):
        for audit in ("AUDIT BLOCKED: missing evidence", ("read_file", {"path": "frontend/src/app.js"})):
            result, requests, _, _ = self.run_boundary(tail=[("browser_probe", {"steps": FLOW}), audit])
            self.assertFalse(result.completed)
            self.assertEqual(len(requests), 7)

    def test_revision_change_invalidates_tail_pass(self):
        result, _, _, _ = self.run_boundary(mutate_at_audit=True)
        self.assertFalse(result.completed)
        self.assertNotIn("AUDIT PASS", result.summary)

    def test_admission_keeps_original_resource_and_stage_gates(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"FACTORY26_COMPLETION_TAIL": "1"}):
            root = Path(directory)
            trace = ProductionTrace(root / "trace.jsonl")
            tools = WorkspaceTools(root, trace, 19449)
            agent = CodingAgent(SimpleNamespace(), tools, trace, max_turns=5)
            tools.last_validation_passed = True
            tools.validation_scope = "quick"
            tools.validated_revision = tools.change_revision
            self.assertTrue(agent._tail_admissible("implementation", ("a",), 0, 0))
            self.assertFalse(agent._tail_admissible("repair", ("a",), 0, 0))
            self.assertFalse(agent._tail_admissible("implementation", (), 0, 0))
            self.assertFalse(agent._tail_admissible("implementation", ("a",), -1, 0))
            self.assertFalse(agent._tail_admissible("implementation", ("a",), 0, agent.maximum_total_tool_calls))
            tools.browser_probe_calls = tools.maximum_browser_probe_calls
            self.assertFalse(agent._tail_admissible("implementation", ("a",), 0, 0))
            tools.browser_probe_verified_revision = 0
            self.assertTrue(agent._tail_admissible("implementation", ("a",), 0, agent.maximum_total_tool_calls))
            tools.last_validation_passed = False
            self.assertFalse(agent._tail_admissible("implementation", ("a",), 0, 0))

    def test_context_limit_never_drops_existing_evidence_for_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = ProductionTrace(root / "trace.jsonl")
            agent = CodingAgent(SimpleNamespace(), WorkspaceTools(root, trace, 19449), trace)
            messages = [{"role": "user", "content": "x" * agent.maximum_context_characters}]
            before = json.dumps(messages)
            self.assertFalse(agent._tail_message(messages, "finish"))
            self.assertEqual(json.dumps(messages), before)

    def test_malformed_or_truncated_probe_is_rejected_before_execution(self):
        for calls in ([], [None], [{"id": "x", "function": []}],
                      [{"id": "", "function": {"name": "browser_probe"}}]):
            self.assertIsNone(_tail_probe_arguments(SimpleNamespace(tool_calls=calls)))
        r = reply(("browser_probe", {"steps": FLOW}), 1)
        r.finish_reason = "length"
        self.assertIsNone(_tail_probe_arguments(r))
        r.finish_reason = "tool_calls"
        r.tool_calls *= 2
        self.assertIsNone(_tail_probe_arguments(r))
        with patch.dict(os.environ, {"FACTORY26_COMPLETION_TAIL": "typo"}):
            with self.assertRaises(ValueError):
                _completion_tail_enabled()


if __name__ == "__main__":
    unittest.main()
