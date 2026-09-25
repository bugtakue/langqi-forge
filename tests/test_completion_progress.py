from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from factory26_harness.agent import CodingAgent
from factory26_harness.checks import CheckResult
from factory26_harness.requirements import RequirementNode
from factory26_harness.trace import ProductionTrace
from factory26_harness.workspace_tools import WorkspaceTools


class CompletionProgressTests(unittest.TestCase):
    def _run_summaries(self, summaries: list[str]):
        class Model:
            def __init__(self):
                self.requests = []

            def complete(self, messages, _schemas):
                self.requests.append([dict(message) for message in messages])
                turn = len(self.requests)
                if turn == 1:
                    name = "write_file"
                    arguments = {
                        "path": "frontend/src/completed.js",
                        "content": "export const completed = true;\n",
                    }
                elif turn == 2:
                    name = "run_validation"
                    arguments = {"scope": "quick"}
                else:
                    content = summaries[min(turn - 3, len(summaries) - 1)]
                    return SimpleNamespace(
                        tool_calls=(), content=content,
                        raw_message={"role": "assistant", "content": content},
                    )
                calls = [{
                    "id": f"call-{turn}", "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }]
                return SimpleNamespace(
                    tool_calls=calls, content="",
                    raw_message={"role": "assistant", "content": "", "tool_calls": calls},
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = ProductionTrace(root / ".arc/trace.jsonl")
            model = Model()
            checks = [CheckResult("fixture", True, "fixture validation", (), 0)]
            # Isolate summary progress from the separate browser-completion policy.
            with patch.dict(os.environ, {"FACTORY26_MAX_BROWSER_PROBES_PER_BATCH": "0"}), patch(
                "factory26_harness.workspace_tools.run_quick_checks", return_value=checks,
            ) as validation:
                tools = WorkspaceTools(root, trace, 33142)
                result = CodingAgent(model, tools, trace, max_turns=8).implement([
                    RequirementNode(
                        "R-COMPLETION", "Completion fixture", "Create one source file.",
                        (), (), (), {},
                    ),
                ])
            validation.assert_called_once()
            self.assertTrue(tools.current_changes_validated)
            rows = [json.loads(line) for line in trace.path.read_text().splitlines()]
            return result, model.requests, rows

    def test_three_invalid_prefix_summaries_stall_after_validation(self):
        summaries = ["Done.", "Implementation finished.", "Verified."]
        result, requests, rows = self._run_summaries(summaries)

        self.assertFalse(result.completed)
        self.assertEqual(result.turns, 5)
        self.assertEqual(len(requests), 5)
        self.assertEqual(result.summary, summaries[-1])
        self.assertEqual(rows[-1]["event"], "agent_session_stalled")
        self.assertEqual(
            rows[-1]["payload"]["reason"],
            "three consecutive no-tool summaries made no accepted progress",
        )
        self.assertNotIn("agent_session_completed", [row["event"] for row in rows])

    def test_invalid_prefix_then_valid_summary_completes(self):
        summary = "AUDIT PASS: fixture validated; no remaining implementation gaps."
        result, requests, rows = self._run_summaries(["Done.", summary])

        self.assertTrue(result.completed)
        self.assertEqual(result.turns, 4)
        self.assertEqual(len(requests), 4)
        self.assertEqual(result.summary, summary)
        self.assertEqual(rows[-1]["event"], "agent_session_completed")
        self.assertNotIn("agent_session_stalled", [row["event"] for row in rows])
        validated_budget_reminders = [
            message["content"] for message in requests[2]
            if message.get("role") == "user"
            and message.get("content", "").startswith("Turn-budget checkpoint: 6 model turns remain.")
        ]
        self.assertEqual(len(validated_budget_reminders), 1)
        self.assertIn("`AUDIT PASS:`", validated_budget_reminders[0])
        self.assertTrue(any(
            message.get("role") == "user"
            and "The acceptance audit is not complete." in message.get("content", "")
            for message in requests[3]
        ))


if __name__ == "__main__":
    unittest.main()
