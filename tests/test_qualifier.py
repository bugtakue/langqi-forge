from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory26_harness import qualifier
from factory26_harness.model import ModelReply
from factory26_harness.requirements import flatten_atomic
from factory26_harness.trace import verify_trace_rows


class ScriptedModel:
    """Protocol fixture only; not evidence of real model ability or GUI quality."""

    def __init__(self, trace) -> None:
        self.trace = trace
        self.request_count = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def gateway_evidence(self) -> dict[str, str]:
        return {"provenance": "scripted-test-fixture", "model": "fixture"}

    def complete(self, messages, tools) -> ModelReply:
        self.request_count += 1
        self.trace.record("model_request", fixture=True, messages=messages)
        if self.request_count == 1:
            calls = [
                {
                    "id": "call-read",
                    "type": "function",
                    "function": {
                        "name": "read_files",
                        "arguments": json.dumps(
                            {
                                "paths": [
                                    "frontend/src/app.js",
                                    "frontend/src/index.html",
                                    "frontend/src/styles.css",
                                    "backend/server.mjs",
                                    "backend/data/state.json",
                                ]
                            }
                        ),
                    },
                }
            ]
        elif self.request_count == 2:
            calls = [
                {
                    "id": "call-edit",
                    "type": "function",
                    "function": {
                        "name": "replace_text",
                        "arguments": json.dumps(
                            {
                                "path": "frontend/src/app.js",
                                "old": "// The coding agent implements the requested application here.",
                                "new": 'document.querySelector("#app").innerHTML = "<h1>Example</h1>";',
                            }
                        ),
                    },
                }
            ]
        elif self.request_count == 3:
            calls = [
                {
                    "id": "call-validate",
                    "type": "function",
                    "function": {
                        "name": "run_validation",
                        "arguments": '{"scope":"quick"}',
                    },
                }
            ]
        else:
            calls = []
        message = {"role": "assistant", "content": "fixture completed", "tool_calls": calls}
        return ModelReply(
            content="fixture completed",
            tool_calls=tuple(calls),
            raw_message=message,
            prompt_tokens=0,
            completion_tokens=0,
            response_id=f"fixture-{self.request_count}",
        )


class QualifierTests(unittest.TestCase):
    def _requirement_dir(self, root: Path) -> Path:
        requirement_dir = root / "requirements"
        requirement_dir.mkdir()
        (requirement_dir / "requirements.yaml").write_text(
            """id: ROOT
name: Example application
type: FOLDER
description: A task-neutral protocol fixture.
children:
  - id: REQ-1
    name: Example heading
    type: ATOMIC
    description: Display one visible heading named Example.
    dependencies: []
    scenarios: []
""",
            encoding="utf-8",
        )
        return requirement_dir

    def test_model_writes_code_and_leaves_sealed_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirement_dir = self._requirement_dir(root)
            output = root / "output"
            with patch.object(qualifier, "OpenAIChatClient", ScriptedModel):
                status = qualifier.main(
                    [str(requirement_dir), "--output-dir", str(output)]
                )
            self.assertEqual(status, 0)
            report = json.loads(
                (output / ".arc" / "harness-report.json").read_text()
            )
            self.assertEqual(report["status"], "local-contract-passed")
            self.assertEqual(report["implemented_requirements"], ["REQ-1"])
            self.assertGreaterEqual(report["model_requests"], 4)
            self.assertIn("<h1>Example</h1>", (output / "frontend/src/app.js").read_text())
            rows = [
                json.loads(line)
                for line in (output / ".arc" / "production-trace.jsonl").read_text().splitlines()
            ]
            self.assertTrue(verify_trace_rows(rows)["valid"])
            self.assertTrue(any(row["event"] == "tool_call" for row in rows))
            if report["arcbench_runtime"] == "official-sdk":
                runner_events = [
                    json.loads(line)
                    for line in (output / ".arc" / "runner-events.jsonl").read_text().splitlines()
                ]
                self.assertTrue(
                    any(
                        event.get("type") == "runner_state"
                        and event.get("state") == "completed"
                        for event in runner_events
                    )
                )
                states = json.loads(
                    (output / ".arc/traceability/node_states.json").read_text()
                )
                self.assertEqual(states["REQ-1"]["state"], "IMPLEMENTED")
                self.assertFalse(report["behavioral_gui_tested"])

    def test_model_gateway_is_required_after_neutral_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirement_dir = self._requirement_dir(root)
            output = root / "output"
            with patch.object(
                qualifier,
                "OpenAIChatClient",
                side_effect=RuntimeError("model unavailable"),
            ):
                status = qualifier.main(
                    [str(requirement_dir), "--output-dir", str(output)]
                )
            self.assertEqual(status, 1)
            report = json.loads(
                (output / ".arc" / "harness-report.json").read_text()
            )
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["implemented_requirements"], [])
            self.assertNotIn("Example", (output / "frontend/src/app.js").read_text())

    def test_preexisting_output_is_rejected_before_model_or_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirement_dir = self._requirement_dir(root)
            output = root / "output"
            output.mkdir()
            (output / "existing.txt").write_text("keep me", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "prior agent work"):
                qualifier.main([str(requirement_dir), "--output-dir", str(output)])
            self.assertEqual((output / "existing.txt").read_text(), "keep me")

    def test_runner_prepopulated_requirements_and_arc_are_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirement_dir = self._requirement_dir(root)
            output = root / "output"
            (output / "requirements").mkdir(parents=True)
            (output / ".arc").mkdir()
            (output / ".arc" / "runner-events.jsonl").write_text("", encoding="utf-8")
            with patch.object(
                qualifier,
                "OpenAIChatClient",
                side_effect=RuntimeError("model unavailable"),
            ):
                status = qualifier.main([str(requirement_dir), "--output-dir", str(output)])
            self.assertEqual(status, 1)
            report = json.loads((output / ".arc" / "harness-report.json").read_text())
            self.assertEqual(report["error"], "model unavailable")

    def test_context_is_data_and_preserved_for_atomic_prompt(self) -> None:
        tree = {
            "id": "ROOT",
            "type": "FOLDER",
            "name": "Container",
            "description": "Relevant product context",
            "children": [
                {
                    "id": "REQ-1",
                    "type": "ATOMIC",
                    "name": "Action",
                    "description": "Implement the action",
                    "dependencies": [],
                }
            ],
        }
        node = qualifier._contextual_nodes(tree, flatten_atomic(tree))[0]
        self.assertIn("Relevant product context", node.description)
        self.assertIn("Implement the action", node.description)


if __name__ == "__main__":
    unittest.main()
