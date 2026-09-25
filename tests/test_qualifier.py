from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory26_harness import qualifier
from factory26_harness.agent import AgentRun
from factory26_harness.checks import CheckResult
from factory26_harness.model import ModelGatewayUnavailable, ModelReply
from factory26_harness.requirements import flatten_atomic
from factory26_harness.trace import verify_trace_rows


class ScriptedModel:
    """Protocol fixture only; not evidence of real model ability or GUI quality."""

    def __init__(self, trace, *, planned_turns: int | None = None) -> None:
        self.trace = trace
        self.planned_turns = planned_turns
        self.request_count = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def gateway_evidence(self) -> dict[str, str]:
        return {"provenance": "scripted-test-fixture", "model": "fixture"}

    def budget_evidence(self) -> dict[str, int | None]:
        return {"planned_turns": self.planned_turns, "max_requests": 64}

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
        message = {"role": "assistant", "content": "AUDIT PASS: fixture completed", "tool_calls": calls}
        return ModelReply(
            content="AUDIT PASS: fixture completed",
            tool_calls=tuple(calls),
            raw_message=message,
            prompt_tokens=0,
            completion_tokens=0,
            response_id=f"fixture-{self.request_count}",
        )


class QualifierTests(unittest.TestCase):
    def test_rejected_startup_candidate_cannot_poison_later_independent_batch(self) -> None:
        class IndependentFixtureAgent:
            def __init__(self, model, tools, _trace, max_turns=20) -> None:
                self.model = model
                self.tools = tools

            def implement(self, nodes, related_files=(), *, task_outline="") -> AgentRun:
                self.model.request_count += 1
                if nodes[0].req_id == "REQ-1":
                    path = "backend/server.mjs"
                    old = "const here = path.dirname(fileURLToPath(import.meta.url));"
                    new = 'throw new Error("uncommitted startup crash");\n' + old
                else:
                    if "uncommitted startup crash" in (
                        self.tools.root / "backend/server.mjs"
                    ).read_text():
                        raise AssertionError("later batch inherited rejected candidate")
                    path = "frontend/src/app.js"
                    old = "// The coding agent implements the requested application here."
                    new = 'document.querySelector("#app").innerHTML = "<h1>Independent</h1>";'
                edited = json.loads(self.tools.execute("replace_text", {
                    "path": path, "old": old, "new": new,
                }))
                if not edited["ok"]:
                    raise AssertionError(edited)
                quick = json.loads(self.tools.execute("run_validation", {"scope": "quick"}))
                if not quick["ok"]:
                    raise AssertionError(quick)
                return AgentRun(True, "quick-only fixture", tuple(self.tools.changed_files), 1)

            def repair(self, _failure_text, _related_files) -> AgentRun:
                return AgentRun(False, "startup repair declined", (), 1)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirements = root / "requirements"
            requirements.mkdir()
            (requirements / "requirements.yaml").write_text(
                "id: ROOT\nname: Two independent features\ntype: FOLDER\nchildren:\n"
                "  - {id: REQ-1, name: First, type: ATOMIC, description: First feature.}\n"
                "  - {id: REQ-2, name: Second, type: ATOMIC, description: Second feature.}\n",
                encoding="utf-8",
            )
            output = root / "output"
            with (
                patch.object(qualifier, "OpenAIChatClient", ScriptedModel),
                patch.object(qualifier, "CodingAgent", IndependentFixtureAgent),
            ):
                status = qualifier.main(
                    [str(requirements), "--output-dir", str(output), "--batch-size", "1"]
                )
            report = json.loads((output / ".arc/harness-report.json").read_text())
            self.assertEqual(status, 0)
            self.assertEqual(report["status"], "local-contract-partial")
            self.assertEqual(report["failed_requirements"], ["REQ-1"])
            self.assertEqual(report["implemented_requirements"], ["REQ-2"])
            self.assertEqual(
                [item["passed_before_repair"] for item in report["candidate_validations"]],
                [False, True],
            )
            self.assertNotIn(
                "uncommitted startup crash", (output / "backend/server.mjs").read_text()
            )
            self.assertIn("<h1>Independent</h1>", (output / "frontend/src/app.js").read_text())

    def test_completed_batch_startup_is_checked_before_promotion_and_repaired_in_isolation(self) -> None:
        class StartupFixtureAgent:
            repair_succeeds = False

            def __init__(self, model, tools, _trace, max_turns=20) -> None:
                self.model = model
                self.tools = tools

            def implement(self, nodes, related_files=(), *, task_outline="") -> AgentRun:
                self.model.request_count += 1
                edited = json.loads(self.tools.execute("replace_text", {
                    "path": "backend/server.mjs",
                    "old": "const here = path.dirname(fileURLToPath(import.meta.url));",
                    "new": (
                        'throw new Error("injected startup failure");\n'
                        "const here = path.dirname(fileURLToPath(import.meta.url));"
                    ),
                }))
                if not edited["ok"]:
                    raise AssertionError(edited)
                quick = json.loads(self.tools.execute("run_validation", {"scope": "quick"}))
                if not quick["ok"]:
                    raise AssertionError(quick)
                return AgentRun(True, "quick-only fixture", tuple(self.tools.changed_files), 1)

            def repair(self, failure_text, related_files) -> AgentRun:
                if "backend exited" not in failure_text:
                    raise AssertionError(failure_text)
                if not type(self).repair_succeeds:
                    return AgentRun(False, "fixture repair refused", (), 1)
                edited = json.loads(self.tools.execute("replace_text", {
                    "path": "backend/server.mjs",
                    "old": 'throw new Error("injected startup failure");\n',
                    "new": "",
                }))
                if not edited["ok"]:
                    raise AssertionError(edited)
                quick = json.loads(self.tools.execute("run_validation", {"scope": "quick"}))
                if not quick["ok"]:
                    raise AssertionError(quick)
                return AgentRun(True, "fixture repaired startup", (), 1)

        for repair_succeeds in (False, True):
            with self.subTest(repair_succeeds=repair_succeeds), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                requirements = root / "requirements"
                requirements.mkdir()
                (requirements / "requirements.yaml").write_text(
                    "id: ROOT\nname: Startup fixture\ntype: FOLDER\nchildren:\n"
                    "  - {id: REQ-1, name: First, type: ATOMIC, description: First feature.}\n",
                    encoding="utf-8",
                )
                output = root / "output"
                StartupFixtureAgent.repair_succeeds = repair_succeeds
                with (
                    patch.object(qualifier, "OpenAIChatClient", ScriptedModel),
                    patch.object(qualifier, "CodingAgent", StartupFixtureAgent),
                ):
                    status = qualifier.main(
                        [str(requirements), "--output-dir", str(output), "--batch-size", "1"]
                    )
                report = json.loads((output / ".arc/harness-report.json").read_text())
                self.assertEqual(status, 0 if repair_succeeds else 1)
                self.assertEqual(report["candidate_validations"], [{
                    "batch": 1,
                    "attempt": 1,
                    "requirement_ids": ["REQ-1"],
                    "passed_before_repair": False,
                    "repair_attempted": True,
                    "passed_after_repair": repair_succeeds,
                }])
                self.assertNotIn(
                    "injected startup failure",
                    (output / "backend/server.mjs").read_text(),
                )
                self.assertEqual(report["implemented_requirements"], ["REQ-1"] if repair_succeeds else [])
                rows = [json.loads(line) for line in
                        (output / ".arc/production-trace.jsonl").read_text().splitlines()]
                self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])
                phases = [row["payload"]["phase"] for row in rows
                          if row["event"] == "implementation_candidate_validation"]
                self.assertEqual(phases, ["before_repair", "after_repair"] if repair_succeeds else ["before_repair"])

    def test_first_batch_gateway_failure_stops_without_claiming_a_scaffold(self) -> None:
        class UnavailableAgent:
            attempted = 0

            def __init__(self, model, tools, _trace, max_turns=20) -> None:
                pass

            def implement(self, nodes, related_files=(), *, task_outline="") -> AgentRun:
                type(self).attempted += 1
                raise ModelGatewayUnavailable("attempt 1: HTTP 401")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirements = root / "requirements"
            requirements.mkdir()
            (requirements / "requirements.yaml").write_text(
                """id: ROOT
name: Gateway failure fixture
type: FOLDER
children:
  - {id: REQ-1, name: First, type: ATOMIC, description: First feature.}
  - {id: REQ-2, name: Second, type: ATOMIC, description: Second feature.}
""",
                encoding="utf-8",
            )
            output = root / "output"
            UnavailableAgent.attempted = 0
            with (
                patch.object(qualifier, "OpenAIChatClient", ScriptedModel),
                patch.object(qualifier, "CodingAgent", UnavailableAgent),
            ):
                status = qualifier.main(
                    [str(requirements), "--output-dir", str(output), "--batch-size", "1"]
                )
            self.assertEqual(status, 1)
            self.assertEqual(UnavailableAgent.attempted, 1)
            report = json.loads((output / ".arc/harness-report.json").read_text())
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["failed_requirements"], ["REQ-1", "REQ-2"])
            self.assertIn("HTTP 401", report["error"])
            self.assertFalse(report["implemented_requirements"])

    def test_model_gateway_failure_preserves_finished_work_without_more_requests(self) -> None:
        class GatewayFailureAgent:
            attempted: list[str] = []

            def __init__(self, model, tools, _trace, max_turns=20) -> None:
                self.model = model
                self.tools = tools

            def implement(self, nodes, related_files=(), *, task_outline="") -> AgentRun:
                req_id = nodes[0].req_id
                type(self).attempted.append(req_id)
                if req_id != "REQ-1":
                    raise ModelGatewayUnavailable("attempt 1: HTTP 401")
                self.model.request_count += 1
                edited = json.loads(self.tools.execute("replace_text", {
                    "path": "frontend/src/app.js",
                    "old": "// The coding agent implements the requested application here.",
                    "new": 'document.querySelector("#app").innerHTML = "<h1>First</h1>";',
                }))
                if not edited["ok"]:
                    raise AssertionError(edited)
                checked = json.loads(self.tools.execute("run_validation", {"scope": "quick"}))
                if not checked["ok"]:
                    raise AssertionError(checked)
                return AgentRun(True, "validated first feature", tuple(self.tools.changed_files), 1)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirements = root / "requirements"
            requirements.mkdir()
            (requirements / "requirements.yaml").write_text(
                """id: ROOT
name: Gateway failure fixture
type: FOLDER
children:
  - {id: REQ-1, name: First, type: ATOMIC, description: First feature.}
  - {id: REQ-2, name: Second, type: ATOMIC, description: Second feature.}
  - {id: REQ-3, name: Third, type: ATOMIC, description: Third feature.}
""",
                encoding="utf-8",
            )
            output = root / "output"
            GatewayFailureAgent.attempted = []
            with (
                patch.object(qualifier, "OpenAIChatClient", ScriptedModel),
                patch.object(qualifier, "CodingAgent", GatewayFailureAgent),
            ):
                status = qualifier.main(
                    [str(requirements), "--output-dir", str(output), "--batch-size", "1"]
                )
            self.assertEqual(status, 0)
            self.assertEqual(GatewayFailureAgent.attempted, ["REQ-1", "REQ-2"])
            report = json.loads((output / ".arc/harness-report.json").read_text())
            self.assertEqual(report["status"], "local-contract-partial")
            self.assertEqual(report["implemented_requirements"], ["REQ-1"])
            self.assertEqual(report["failed_requirements"], ["REQ-2", "REQ-3"])
            self.assertEqual(report["model_gateway_stop_reason"], "attempt 1: HTTP 401")
            self.assertIn("<h1>First</h1>", (output / "frontend/src/app.js").read_text())
            rows = [json.loads(line) for line in
                    (output / ".arc/production-trace.jsonl").read_text().splitlines()]
            self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])
            self.assertTrue(any(row["event"] == "model_gateway_circuit_open" for row in rows))
            skipped = next(row for row in rows if row["event"] == "implementation_skipped_after_model_failure")
            self.assertEqual(skipped["payload"]["requirement_ids"], ["REQ-3"])
            if report["arcbench_runtime"] == "official-sdk":
                states = json.loads((output / ".arc/traceability/node_states.json").read_text())
                self.assertEqual([states[f"REQ-{index}"]["state"] for index in range(1, 4)],
                                 ["IMPLEMENTED", "FAILED", "FAILED"])

    def test_failed_four_node_batch_salvages_validated_half(self) -> None:
        class SplitFixtureAgent:
            attempted: list[tuple[str, ...]] = []
            observed_notes: list[tuple[str, ...]] = []

            def __init__(self, model, tools, _trace, max_turns=20) -> None:
                self.model = model
                self.tools = tools

            def implement(self, nodes, related_files=(), *, task_outline="") -> AgentRun:
                ids = tuple(node.req_id for node in nodes)
                type(self).attempted.append(ids)
                type(self).observed_notes.append(self.tools.handoff_notes)
                self.model.request_count += 1
                if ids == ("REQ-1", "REQ-2", "REQ-3", "REQ-4"):
                    replacement = "<h1>Discard this failed whole-batch edit</h1>"
                elif ids == ("REQ-1", "REQ-2"):
                    replacement = "<h1>Validated first half</h1>"
                elif ids == ("REQ-3", "REQ-4"):
                    replacement = "<h1>Discard this failed second-half edit</h1>"
                else:
                    raise AssertionError(ids)
                changed = json.loads(self.tools.execute(
                    "replace_text",
                    {
                        "path": "frontend/src/app.js",
                        "old": (
                            "<h1>Validated first half</h1>"
                            if ids == ("REQ-3", "REQ-4")
                            else "// The coding agent implements the requested application here."
                        ),
                        "new": f'document.querySelector("#app").innerHTML = "{replacement}";',
                    },
                ))
                self.assert_change(changed)
                if ids == ("REQ-1", "REQ-2"):
                    validated = json.loads(self.tools.execute("run_validation", {"scope": "quick"}))
                    self.assert_change(validated)
                    return AgentRun(True, "first half validated", tuple(self.tools.changed_files), 1)
                return AgentRun(False, "fixture stopped", tuple(self.tools.changed_files), 1)

            @staticmethod
            def assert_change(result: dict) -> None:
                if not result["ok"]:
                    raise AssertionError(result)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirements = root / "requirements"
            requirements.mkdir()
            (requirements / "requirements.yaml").write_text(
                """id: ROOT
name: Salvage fixture
type: FOLDER
children:
  - {id: REQ-1, name: First, type: ATOMIC, description: First feature.}
  - {id: REQ-2, name: Second, type: ATOMIC, description: Second feature., dependencies: [REQ-1]}
  - {id: REQ-3, name: Third, type: ATOMIC, description: Third feature.}
  - {id: REQ-4, name: Fourth, type: ATOMIC, description: Fourth feature., dependencies: [REQ-3]}
""",
                encoding="utf-8",
            )
            output = root / "output"
            SplitFixtureAgent.attempted = []
            SplitFixtureAgent.observed_notes = []
            with (
                patch.object(qualifier, "OpenAIChatClient", ScriptedModel),
                patch.object(qualifier, "CodingAgent", SplitFixtureAgent),
            ):
                status = qualifier.main([str(requirements), "--output-dir", str(output)])
            self.assertEqual(status, 0)
            self.assertEqual(SplitFixtureAgent.attempted, [
                ("REQ-1", "REQ-2", "REQ-3", "REQ-4"),
                ("REQ-1", "REQ-2"),
                ("REQ-3", "REQ-4"),
            ])
            self.assertEqual(SplitFixtureAgent.observed_notes[:2], [(), ()])
            self.assertIn("first half validated", SplitFixtureAgent.observed_notes[2][0])
            self.assertNotIn("fixture stopped", SplitFixtureAgent.observed_notes[2][0])
            report = json.loads((output / ".arc/harness-report.json").read_text())
            self.assertEqual(report["status"], "local-contract-partial")
            self.assertEqual(report["salvage_attempts"], 2)
            self.assertEqual(report["implemented_requirements"], ["REQ-1", "REQ-2"])
            self.assertEqual(report["failed_requirements"], ["REQ-3", "REQ-4"])
            self.assertEqual(
                [item["committed"] for item in report["browser_probe_batches"]],
                [False, True, False],
            )
            source = (output / "frontend/src/app.js").read_text()
            self.assertIn("Validated first half", source)
            self.assertNotIn("Discard this", source)
            rows = [json.loads(line) for line in (output / ".arc/production-trace.jsonl").read_text().splitlines()]
            self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])
            split = next(row for row in rows if row["event"] == "implementation_batch_split")
            self.assertEqual(split["payload"]["retry_groups"], [["REQ-1", "REQ-2"], ["REQ-3", "REQ-4"]])
            if report["arcbench_runtime"] == "official-sdk":
                states = json.loads((output / ".arc/traceability/node_states.json").read_text())
                self.assertEqual([states[f"REQ-{i}"]["state"] for i in range(1, 5)], [
                    "IMPLEMENTED", "IMPLEMENTED", "FAILED", "FAILED",
                ])

    def test_split_retry_blocks_dependents_but_runs_independent_node(self) -> None:
        class DependencyFixtureAgent:
            attempted: list[tuple[str, ...]] = []

            def __init__(self, model, tools, _trace, max_turns=20) -> None:
                self.model = model
                self.tools = tools

            def implement(self, nodes, related_files=(), *, task_outline="") -> AgentRun:
                ids = tuple(node.req_id for node in nodes)
                type(self).attempted.append(ids)
                self.model.request_count += 1
                if ids != ("REQ-4",):
                    return AgentRun(False, "fixture failed", (), 1)
                changed = json.loads(self.tools.execute("replace_text", {
                    "path": "frontend/src/app.js",
                    "old": "// The coding agent implements the requested application here.",
                    "new": 'document.querySelector("#app").innerHTML = "<h1>Independent</h1>";',
                }))
                if not changed["ok"]:
                    raise AssertionError(changed)
                validated = json.loads(self.tools.execute("run_validation", {"scope": "quick"}))
                if not validated["ok"]:
                    raise AssertionError(validated)
                return AgentRun(True, "independent node validated", tuple(self.tools.changed_files), 1)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirements = root / "requirements"
            requirements.mkdir()
            (requirements / "requirements.yaml").write_text(
                """id: ROOT
name: Dependency fixture
type: FOLDER
children:
  - {id: REQ-1, name: First, type: ATOMIC, description: First feature.}
  - {id: REQ-2, name: Second, type: ATOMIC, description: Second feature.}
  - {id: REQ-3, name: Dependent, type: ATOMIC, description: Needs first., dependencies: [REQ-1]}
  - {id: REQ-4, name: Independent, type: ATOMIC, description: Independent feature.}
""",
                encoding="utf-8",
            )
            output = root / "output"
            DependencyFixtureAgent.attempted = []
            with (
                patch.object(qualifier, "OpenAIChatClient", ScriptedModel),
                patch.object(qualifier, "CodingAgent", DependencyFixtureAgent),
            ):
                status = qualifier.main([str(requirements), "--output-dir", str(output)])
            self.assertEqual(status, 0)
            self.assertEqual(DependencyFixtureAgent.attempted, [
                ("REQ-1", "REQ-2", "REQ-3", "REQ-4"),
                ("REQ-1", "REQ-2"),
                ("REQ-4",),
            ])
            report = json.loads((output / ".arc/harness-report.json").read_text())
            self.assertEqual(report["implemented_requirements"], ["REQ-4"])
            self.assertEqual(report["failed_requirements"], ["REQ-1", "REQ-2", "REQ-3"])
            self.assertEqual(report["salvage_attempts"], 2)
            self.assertIn("Independent", (output / "frontend/src/app.js").read_text())
            rows = [json.loads(line) for line in (output / ".arc/production-trace.jsonl").read_text().splitlines()]
            self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])
            self.assertTrue(any(row["event"] == "implementation_dependency_blocked" for row in rows))

    def test_salvage_attempts_are_bounded_and_can_be_disabled(self) -> None:
        class AlwaysFailAgent:
            attempted: list[tuple[str, ...]] = []

            def __init__(self, model, tools, _trace, max_turns=20) -> None:
                self.model = model

            def implement(self, nodes, related_files=(), *, task_outline="") -> AgentRun:
                type(self).attempted.append(tuple(node.req_id for node in nodes))
                self.model.request_count += 1
                return AgentRun(False, "fixture failed", (), 1)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirements = root / "requirements"
            requirements.mkdir()
            (requirements / "requirements.yaml").write_text(
                """id: ROOT
name: Retry limit fixture
type: FOLDER
children:
  - {id: REQ-1, name: First, type: ATOMIC, description: First feature.}
  - {id: REQ-2, name: Second, type: ATOMIC, description: Second feature.}
""",
                encoding="utf-8",
            )
            for salvage_splits, expected_attempts in (
                ("1", [("REQ-1", "REQ-2"), ("REQ-1",), ("REQ-2",)]),
                ("0", [("REQ-1", "REQ-2")]),
            ):
                with self.subTest(salvage_splits=salvage_splits):
                    AlwaysFailAgent.attempted = []
                    output = root / f"output-{salvage_splits}"
                    with (
                        patch.object(qualifier, "OpenAIChatClient", ScriptedModel),
                        patch.object(qualifier, "CodingAgent", AlwaysFailAgent),
                    ):
                        status = qualifier.main([
                            str(requirements), "--output-dir", str(output),
                            "--salvage-splits", salvage_splits,
                        ])
                    self.assertEqual(status, 1)
                    self.assertEqual(AlwaysFailAgent.attempted, expected_attempts)
                    report = json.loads((output / ".arc/harness-report.json").read_text())
                    self.assertEqual(report["failed_requirements"], ["REQ-1", "REQ-2"])
                    self.assertEqual(report["salvage_attempts"], len(expected_attempts) - 1)
                    rows = [json.loads(line) for line in (output / ".arc/production-trace.jsonl").read_text().splitlines()]
                    self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])
                    self.assertEqual(
                        sum(row["event"] == "implementation_batch_split" for row in rows),
                        int(salvage_splits),
                    )

    def test_model_runtime_error_does_not_trigger_split_retry(self) -> None:
        class BrokenGatewayAgent:
            attempted = 0

            def __init__(self, model, tools, _trace, max_turns=20) -> None:
                self.model = model

            def implement(self, nodes, related_files=(), *, task_outline="") -> AgentRun:
                type(self).attempted += 1
                self.model.request_count += 1
                raise RuntimeError("fixture model gateway unavailable")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirements = root / "requirements"
            requirements.mkdir()
            (requirements / "requirements.yaml").write_text(
                """id: ROOT
name: Gateway fixture
type: FOLDER
children:
  - {id: REQ-1, name: First, type: ATOMIC, description: First feature.}
  - {id: REQ-2, name: Second, type: ATOMIC, description: Second feature.}
""",
                encoding="utf-8",
            )
            output = root / "output"
            BrokenGatewayAgent.attempted = 0
            with (
                patch.object(qualifier, "OpenAIChatClient", ScriptedModel),
                patch.object(qualifier, "CodingAgent", BrokenGatewayAgent),
            ):
                status = qualifier.main([str(requirements), "--output-dir", str(output)])
            self.assertEqual(status, 1)
            self.assertEqual(BrokenGatewayAgent.attempted, 1)
            report = json.loads((output / ".arc/harness-report.json").read_text())
            self.assertEqual(report["salvage_attempts"], 0)
            self.assertEqual(report["failed_requirements"], ["REQ-1", "REQ-2"])

    def test_failed_batch_drops_its_edits_and_keeps_independent_credit(self) -> None:
        class PartialFixtureAgent:
            attempted: list[str] = []

            def __init__(self, model, tools, _trace, max_turns=20) -> None:
                self.model = model
                self.tools = tools

            def implement(self, nodes, related_files=(), *, task_outline="") -> AgentRun:
                req_id = nodes[0].req_id
                type(self).attempted.append(req_id)
                self.model.request_count += 1
                if req_id == "REQ-1":
                    old, new = (
                        "// The coding agent implements the requested application here.",
                        'document.querySelector("#app").innerHTML = "<h1>First</h1>";',
                    )
                elif req_id == "REQ-2":
                    old, new = "<h1>First</h1>", "<h1>Poison</h1>"
                elif req_id == "REQ-4":
                    old, new = "<h1>First</h1>", "<h1>Final</h1>"
                else:
                    raise AssertionError("dependent REQ-3 should not be attempted")
                edited = json.loads(
                    self.tools.execute(
                        "replace_text",
                        {"path": "frontend/src/app.js", "old": old, "new": new},
                    )
                )
                if not edited["ok"]:
                    raise AssertionError(edited)
                if req_id == "REQ-2":
                    return AgentRun(False, "fixture stopped before validation", tuple(self.tools.changed_files), 1)
                validated = json.loads(self.tools.execute("run_validation", {"scope": "quick"}))
                if not validated["ok"]:
                    raise AssertionError(validated)
                return AgentRun(True, "fixture validated", tuple(self.tools.changed_files), 1)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirements = root / "requirements"
            requirements.mkdir()
            (requirements / "requirements.yaml").write_text(
                """id: ROOT
name: Partial credit fixture
type: FOLDER
children:
  - {id: REQ-1, name: Foundation, type: ATOMIC, description: Create a heading.}
  - {id: REQ-2, name: Failing feature, type: ATOMIC, description: Edit the heading.}
  - {id: REQ-3, name: Dependent feature, type: ATOMIC, description: Depends on failure, dependencies: [REQ-2]}
  - {id: REQ-4, name: Independent feature, type: ATOMIC, description: Extend foundation, dependencies: [REQ-1]}
""",
                encoding="utf-8",
            )
            output = root / "output"
            PartialFixtureAgent.attempted = []
            with (
                patch.object(qualifier, "OpenAIChatClient", ScriptedModel),
                patch.object(qualifier, "CodingAgent", PartialFixtureAgent),
            ):
                status = qualifier.main(
                    [str(requirements), "--output-dir", str(output), "--batch-size", "1"]
                )
            self.assertEqual(status, 0)
            self.assertEqual(PartialFixtureAgent.attempted, ["REQ-1", "REQ-2", "REQ-4"])
            report = json.loads((output / ".arc/harness-report.json").read_text())
            self.assertEqual(report["status"], "local-contract-partial")
            self.assertEqual(report["implemented_requirements"], ["REQ-1", "REQ-4"])
            self.assertEqual(report["failed_requirements"], ["REQ-2", "REQ-3"])
            self.assertFalse(report["browser_probe_batches"][1]["committed"])
            app = (output / "frontend/src/app.js").read_text()
            self.assertIn("<h1>Final</h1>", app)
            self.assertNotIn("Poison", app)
            rows = [
                json.loads(line)
                for line in (output / ".arc/production-trace.jsonl").read_text().splitlines()
            ]
            self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])
            self.assertTrue(
                any(row["event"] == "implementation_dependency_blocked" for row in rows)
            )
            if report["arcbench_runtime"] == "official-sdk":
                states = json.loads((output / ".arc/traceability/node_states.json").read_text())
                self.assertEqual(states["REQ-1"]["state"], "IMPLEMENTED")
                self.assertEqual(states["REQ-2"]["state"], "FAILED")
                self.assertEqual(states["REQ-3"]["state"], "FAILED")
                self.assertEqual(states["REQ-4"]["state"], "IMPLEMENTED")
                committed_states = json.loads(
                    subprocess.check_output(
                        [
                            "git", "-C", str(output), "show",
                            "HEAD:.arc/traceability/node_states.json",
                        ],
                        text=True,
                    )
                )
                self.assertEqual(committed_states["REQ-2"]["state"], "FAILED")
                self.assertEqual(committed_states["REQ-3"]["state"], "FAILED")

    def test_no_completed_batch_still_fails_closed(self) -> None:
        class FailingFixtureAgent:
            def __init__(self, model, tools, _trace, max_turns=20) -> None:
                self.model = model
                self.tools = tools

            def implement(self, nodes, related_files=(), *, task_outline="") -> AgentRun:
                self.model.request_count += 1
                return AgentRun(False, "fixture did not implement", (), 1)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirement_dir = self._requirement_dir(root)
            output = root / "output"
            with (
                patch.object(qualifier, "OpenAIChatClient", ScriptedModel),
                patch.object(qualifier, "CodingAgent", FailingFixtureAgent),
            ):
                status = qualifier.main([str(requirement_dir), "--output-dir", str(output)])
            self.assertEqual(status, 1)
            report = json.loads((output / ".arc/harness-report.json").read_text())
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["implemented_requirements"], [])
            self.assertEqual(report["failed_requirements"], ["REQ-1"])
            self.assertIn(
                "The coding agent implements the requested application here",
                (output / "frontend/src/app.js").read_text(),
            )

    def test_behavioral_probe_claim_requires_final_repair_probe(self) -> None:
        report = {
            "browser_probe_batches": [{"behavioral_probe_verified": True}],
            "browser_probe_repairs": [],
        }
        self.assertTrue(qualifier._behavioral_probe_tested(report))
        report["browser_probe_repairs"].append(
            {
                "changed_files": ["frontend/src/app.js"],
                "behavioral_probe_verified": False,
            }
        )
        self.assertFalse(qualifier._behavioral_probe_tested(report))
        report["browser_probe_repairs"][0]["behavioral_probe_verified"] = True
        self.assertTrue(qualifier._behavioral_probe_tested(report))
        report["browser_probe_batches"].append(
            {"committed": False, "behavioral_probe_verified": False}
        )
        self.assertTrue(qualifier._behavioral_probe_tested(report))
        report["browser_probe_repairs"].append(
            {
                "committed": False,
                "changed_files": ["frontend/src/styles.css"],
                "behavioral_probe_verified": False,
            }
        )
        self.assertTrue(qualifier._behavioral_probe_tested(report))

    def test_final_repair_without_new_probe_is_reported_unverified(self) -> None:
        class RepairFixtureAgent:
            def __init__(self, model, tools, _trace, max_turns=20) -> None:
                self.model = model
                self.tools = tools

            def _edit(self, old: str, new: str) -> AgentRun:
                changed = json.loads(
                    self.tools.execute(
                        "replace_text",
                        {"path": "frontend/src/app.js", "old": old, "new": new},
                    )
                )
                if not changed["ok"]:
                    raise AssertionError(changed)
                validated = json.loads(
                    self.tools.execute("run_validation", {"scope": "quick"})
                )
                if not validated["ok"]:
                    raise AssertionError(validated)
                self.model.request_count += 1
                return AgentRun(True, "repair fixture", tuple(self.tools.changed_files), 1)

            def implement(self, _nodes, related_files=(), *, task_outline="") -> AgentRun:
                result = self._edit(
                    "// The coding agent implements the requested application here.",
                    'document.querySelector("#app").innerHTML = "<h1>Example</h1>";',
                )
                self.tools.browser_probe_calls = 1
                self.tools.browser_probe_verified_revision = self.tools.change_revision
                return result

            def repair(self, _failure_text, _related_files) -> AgentRun:
                return self._edit("<h1>Example</h1>", "<h1>Example repaired</h1>")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirement_dir = self._requirement_dir(root)
            output = root / "output"
            actual_checks = qualifier.run_full_checks
            calls = 0

            def force_one_repair(path: Path, port: int):
                nonlocal calls
                calls += 1
                if calls == 3:
                    return [
                        qualifier.CheckResult(
                            "forced_repair", False, "fixture repair needed",
                            ("frontend/src/app.js",), 0.0,
                        )
                    ]
                return actual_checks(path, port)

            with (
                patch.object(qualifier, "OpenAIChatClient", ScriptedModel),
                patch.object(qualifier, "CodingAgent", RepairFixtureAgent),
                patch.object(qualifier, "run_full_checks", force_one_repair),
            ):
                status = qualifier.main([str(requirement_dir), "--output-dir", str(output)])
            self.assertEqual(status, 0)
            report = json.loads((output / ".arc/harness-report.json").read_text())
            self.assertTrue(report["browser_probe_batches"][0]["behavioral_probe_verified"])
            self.assertEqual(report["browser_probe_repairs"][0]["calls"], 0)
            self.assertFalse(report["browser_probe_repairs"][0]["behavioral_probe_verified"])
            self.assertFalse(report["behavioral_probe_tested"])
            rows = [
                json.loads(line)
                for line in (output / ".arc/production-trace.jsonl").read_text().splitlines()
            ]
            repair_event = next(row for row in rows if row["event"] == "repair_finished")
            self.assertFalse(repair_event["payload"]["browser_probe"]["behavioral_probe_verified"])
            self.assertTrue(repair_event["payload"]["staged_changes_committed"])
            self.assertTrue(any(row["event"] == "repair_candidate_validation" for row in rows))

    def test_failed_repair_never_overwrites_last_committed_app(self) -> None:
        class RepairFixtureAgent:
            complete_repair = False

            def __init__(self, model, tools, _trace, max_turns=20) -> None:
                self.model = model
                self.tools = tools

            def implement(self, _nodes, related_files=(), *, task_outline="") -> AgentRun:
                edited = json.loads(self.tools.execute("replace_text", {
                    "path": "frontend/src/app.js",
                    "old": "// The coding agent implements the requested application here.",
                    "new": 'document.querySelector("#app").innerHTML = "<h1>Committed</h1>";',
                }))
                self.assert_edit(edited)
                validated = json.loads(self.tools.execute("run_validation", {"scope": "quick"}))
                self.assert_edit(validated)
                self.model.request_count += 1
                return AgentRun(True, "implemented", tuple(self.tools.changed_files), 1)

            def repair(self, _failure_text, _related_files) -> AgentRun:
                edited = json.loads(self.tools.execute("replace_text", {
                    "path": "frontend/src/app.js",
                    "old": "<h1>Committed</h1>",
                    "new": "<h1>Uncommitted repair</h1>",
                }))
                self.assert_edit(edited)
                return AgentRun(
                    self.complete_repair,
                    "repair attempted",
                    tuple(self.tools.changed_files),
                    1,
                )

            @staticmethod
            def assert_edit(result: dict) -> None:
                if not result["ok"]:
                    raise AssertionError(result)

        for complete_repair in (False, True):
            with self.subTest(complete_repair=complete_repair):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    requirement_dir = self._requirement_dir(root)
                    output = root / "output"
                    actual_checks = qualifier.run_full_checks
                    calls = 0

                    def fail_final_and_candidate(path: Path, port: int):
                        nonlocal calls
                        calls += 1
                        if calls >= 3:
                            return [qualifier.CheckResult(
                                "forced_repair", False, "fixture repair still fails",
                                ("frontend/src/app.js",), 0.0,
                            )]
                        return actual_checks(path, port)

                    RepairFixtureAgent.complete_repair = complete_repair
                    with (
                        patch.object(qualifier, "OpenAIChatClient", ScriptedModel),
                        patch.object(qualifier, "CodingAgent", RepairFixtureAgent),
                        patch.object(qualifier, "run_full_checks", fail_final_and_candidate),
                    ):
                        status = qualifier.main([
                            str(requirement_dir), "--output-dir", str(output),
                        ])
                    self.assertEqual(status, 1)
                    self.assertIn(
                        "<h1>Committed</h1>",
                        (output / "frontend/src/app.js").read_text(),
                    )
                    self.assertNotIn(
                        "Uncommitted repair",
                        (output / "frontend/src/app.js").read_text(),
                    )
                    report = json.loads((output / ".arc/harness-report.json").read_text())
                    self.assertFalse(report["browser_probe_repairs"][0]["committed"])
                    self.assertEqual(calls, 4 if complete_repair else 3)

    def test_run_failure_is_reported_even_when_requirement_failure_event_raises(self) -> None:
        class BrokenRuntime:
            def __init__(self) -> None:
                self.events: list[tuple[str, object]] = []

            def fail_batch(self, requirement_ids, _reason) -> None:
                self.events.append(("batch", list(requirement_ids)))
                raise RuntimeError("state writer unavailable")

            def fail(self, reason) -> None:
                self.events.append(("run", reason))

        runtime = BrokenRuntime()
        errors = qualifier._report_arc_failure(runtime, ["REQ-1"], "commit failed")
        self.assertEqual(runtime.events, [("batch", ["REQ-1"]), ("run", "commit failed")])
        self.assertEqual(errors, ["requirement failure event: state writer unavailable"])

    def test_both_sdk_failure_reporting_errors_are_preserved(self) -> None:
        class BrokenRuntime:
            def fail_batch(self, _requirement_ids, _reason) -> None:
                raise RuntimeError("node error")

            def fail(self, _reason) -> None:
                raise RuntimeError("run error")

        self.assertEqual(
            qualifier._report_arc_failure(BrokenRuntime(), ["REQ-1"], "failed"),
            ["requirement failure event: node error", "run failure event: run error"],
        )

    def test_cross_batch_handoff_tracks_recent_generated_files(self) -> None:
        paths = qualifier._recent_handoff_paths(
            ["frontend/src/older.js", "frontend/src/app.js"],
            ["frontend/src/older.js", "backend/routes/notes.mjs"],
        )
        self.assertEqual(
            paths,
            [
                "frontend/src/app.js",
                "frontend/src/older.js",
                "backend/routes/notes.mjs",
            ],
        )
        many = qualifier._recent_handoff_paths(
            [], (f"frontend/src/feature-{index}.js" for index in range(100))
        )
        self.assertEqual(len(many), qualifier.MAX_HANDOFF_PATHS)
        self.assertEqual(many[0], "frontend/src/feature-40.js")

    def test_successful_batch_handoffs_are_bounded_and_recent(self) -> None:
        notes: tuple[str, ...] = ()
        for index in range(10):
            notes = qualifier._recent_handoff_notes(
                notes,
                [f"REQ-{index}"],
                "AUDIT PASS: state contract " + "x" * 2000,
            )
        self.assertLessEqual(len(notes), qualifier.MAX_HANDOFF_NOTES)
        self.assertLessEqual(sum(map(len, notes)), qualifier.MAX_HANDOFF_NOTES_CHARS)
        self.assertTrue(notes[-1].startswith("REQ-9:"))
        self.assertNotIn("REQ-0:", " ".join(notes))

    def test_second_batch_receives_first_batch_source_path(self) -> None:
        class WritingAgent:
            observed: list[tuple[str, ...]] = []
            outlines: list[dict] = []
            notes: list[tuple[str, ...]] = []

            def __init__(self, model, tools, _trace, max_turns=20) -> None:
                self.model = model
                self.tools = tools

            def implement(self, nodes, related_files=(), *, task_outline="") -> AgentRun:
                type(self).observed.append(tuple(related_files))
                type(self).outlines.append(json.loads(task_outline))
                type(self).notes.append(self.tools.handoff_notes)
                name = "first" if nodes[0].req_id == "REQ-1" else "second"
                written = json.loads(
                    self.tools.execute(
                        "write_file",
                        {
                            "path": f"frontend/src/{name}.js",
                            "content": f"export const {name} = true;\n",
                        },
                    )
                )
                self.assert_write(written)
                validated = json.loads(
                    self.tools.execute("run_validation", {"scope": "quick"})
                )
                self.assert_write(validated)
                self.model.request_count += 1
                return AgentRun(
                    True,
                    "AUDIT PASS: canonical state in backend/data/state.json; route POST /api/example",
                    tuple(sorted(self.tools.changed_files)),
                    1,
                )

            @staticmethod
            def assert_write(result: dict) -> None:
                if not result["ok"]:
                    raise AssertionError(result)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirements = root / "requirements"
            requirements.mkdir()
            (requirements / "requirements.yaml").write_text(
                """id: ROOT
name: Two batches
type: FOLDER
children:
  - id: REQ-1
    name: First
    type: ATOMIC
    description: Create a feature.
  - id: MODULE-2
    name: Later module
    type: FOLDER
    dependencies: [REQ-1]
    children:
      - id: REQ-2
        name: Second
        type: ATOMIC
        description: Extend the feature.
""",
                encoding="utf-8",
            )
            WritingAgent.observed = []
            WritingAgent.outlines = []
            WritingAgent.notes = []
            with (
                patch.object(qualifier, "OpenAIChatClient", ScriptedModel),
                patch.object(qualifier, "CodingAgent", WritingAgent),
            ):
                status = qualifier.main(
                    [
                        str(requirements),
                        "--output-dir",
                        str(root / "output"),
                        "--batch-size",
                        "1",
                    ]
                )
            self.assertEqual(status, 0)
            self.assertEqual(WritingAgent.observed[0], ())
            self.assertIn("frontend/src/first.js", WritingAgent.observed[1])
            self.assertEqual(WritingAgent.notes[0], ())
            self.assertIn("POST /api/example", WritingAgent.notes[1][0])
            self.assertEqual(
                [item["listed_requirements"] for item in WritingAgent.outlines],
                [2, 2],
            )
            self.assertEqual(
                [entry["id"] for entry in WritingAgent.outlines[0]["requirements"]],
                ["REQ-1", "REQ-2"],
            )
            self.assertEqual(
                WritingAgent.outlines[0]["folder_dependencies"],
                [{"id": "MODULE-2", "name": "Later module", "dependencies": ["REQ-1"]}],
            )
            compiled_plan = json.loads(
                (root / "output" / ".arc" / "compiled-plan.json").read_text(encoding="utf-8")
            )
            self.assertEqual(compiled_plan["folder_dependencies"], WritingAgent.outlines[0]["folder_dependencies"])
            self.assertEqual(compiled_plan["batches"], [["REQ-1"], ["REQ-2"]])
            rows = [
                json.loads(line)
                for line in (root / "output" / ".arc" / "production-trace.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            started = [row for row in rows if row["event"] == "implementation_batch_started"]
            self.assertIn("frontend/src/first.js", started[1]["payload"]["prior_source_paths"])

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

    def test_initial_scaffold_failure_retains_exact_check_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirement_dir = self._requirement_dir(root)
            output = root / "output"
            failure = CheckResult(
                "startup_health", False, "smoke port occupied",
                ("backend/server.mjs",), 0.0,
            )
            with patch.object(qualifier, "run_full_checks", return_value=[failure]):
                status = qualifier.main(
                    [str(requirement_dir), "--output-dir", str(output)]
                )
            report = json.loads(
                (output / ".arc" / "harness-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status, 1)
            self.assertEqual(report.get("model_requests", 0), 0)
            self.assertEqual(report["initial_checks"][0]["summary"], "smoke port occupied")
            self.assertFalse(report["initial_checks"][0]["passed"])

    def test_initial_scaffold_retries_only_an_occupied_smoke_port(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirement_dir = self._requirement_dir(root)
            output = root / "output"
            ports: list[int] = []
            while len(ports) < 2:
                candidate = qualifier._smoke_port(3000)
                if candidate not in ports:
                    ports.append(candidate)
            actual_full_checks = qualifier.run_full_checks
            checked_ports: list[int] = []

            def first_port_is_taken(project: Path, port: int):
                checked_ports.append(port)
                if len(checked_ports) == 1:
                    return [CheckResult(
                        "startup_health", False,
                        f"smoke port {port} is already occupied",
                        ("backend/server.mjs",), 0.0,
                    )]
                return actual_full_checks(project, port)

            with (
                patch.object(qualifier, "_smoke_port", side_effect=ports),
                patch.object(qualifier, "run_full_checks", side_effect=first_port_is_taken),
                patch.object(qualifier, "OpenAIChatClient", ScriptedModel),
            ):
                status = qualifier.main(
                    [str(requirement_dir), "--output-dir", str(output)]
                )
            report = json.loads(
                (output / ".arc" / "harness-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status, 0, report)
            self.assertEqual(checked_ports[:2], ports)
            self.assertEqual(len(report["initial_check_attempts"]), 2)
            self.assertFalse(report["initial_check_attempts"][0][-1]["passed"])
            self.assertTrue(all(item["passed"] for item in report["initial_checks"]))

    def test_model_writes_code_and_leaves_sealed_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirement_dir = self._requirement_dir(root)
            output = root / "output"
            with patch.object(qualifier, "OpenAIChatClient", ScriptedModel):
                status = qualifier.main(
                    [str(requirement_dir), "--output-dir", str(output)]
                )
            report = json.loads(
                (output / ".arc" / "harness-report.json").read_text()
            )
            self.assertEqual(status, 0, report)
            self.assertEqual(report["status"], "local-contract-passed")
            self.assertEqual(report["evidence_export"]["status"], "exported")
            self.assertTrue((output / report["evidence_export"]["path"]).is_file())
            self.assertEqual(len(report["initial_checks"]), 6)
            self.assertTrue(all(item["passed"] for item in report["initial_checks"]))
            self.assertEqual(report["implemented_requirements"], ["REQ-1"])
            self.assertFalse(report["behavioral_probe_tested"])
            self.assertFalse(report["behavioral_gui_tested"])
            self.assertEqual(report["browser_probe_batches"][0]["calls"], 0)
            self.assertGreaterEqual(report["model_requests"], 4)
            self.assertEqual(report["model_budget"]["planned_turns"], 160)
            self.assertTrue(report["candidate_validations"][0]["passed_before_repair"])
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
            self.assertEqual(report["evidence_export"]["status"], "exported")
            self.assertTrue((output / report["evidence_export"]["path"]).is_file())
            self.assertEqual(report["implemented_requirements"], [])
            self.assertNotIn("Example", (output / "frontend/src/app.js").read_text())

    def test_evidence_export_failure_does_not_discard_a_working_application(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirement_dir = self._requirement_dir(root)
            output = root / "output"
            with patch.object(qualifier, "OpenAIChatClient", ScriptedModel), patch.object(
                qualifier.ProductionTrace, "export_evidence",
                side_effect=OSError("private error text must not be echoed"),
            ):
                status = qualifier.main([str(requirement_dir), "--output-dir", str(output)])
            report = json.loads((output / ".arc/harness-report.json").read_text())
            self.assertEqual(status, 0)
            self.assertEqual(report["status"], "local-contract-passed")
            self.assertEqual(report["evidence_export"], {"status": "failed", "error_type": "OSError"})
            self.assertFalse((output / "factory26-evidence.zip").exists())

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

    def test_explicit_visual_reference_field_reaches_batch_image_inventory(self) -> None:
        tree = {
            "id": "ROOT",
            "type": "FOLDER",
            "name": "Container",
            "description": "Parent image ![image](./reference/parent.jpg)",
            "visual_reference": ["./reference/parent-listed.webp"],
            "children": [
                {
                    "id": "REQ-1",
                    "type": "ATOMIC",
                    "name": "Action",
                    "description": "Implement the action.",
                    "visual_reference": [
                        "./reference/only-listed.png",
                        "reference/parent.jpg",
                    ],
                }
            ],
        }
        nodes = qualifier._contextual_nodes(tree, flatten_atomic(tree))
        self.assertEqual(
            qualifier._named_reference_images(nodes),
            (
                "reference/only-listed.png",
                "reference/parent-listed.webp",
                "reference/parent.jpg",
            ),
        )

    def test_explicit_visual_reference_is_available_to_real_batch_tools(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirement_dir = root / "requirements"
            reference_dir = requirement_dir / "reference"
            reference_dir.mkdir(parents=True)
            (requirement_dir / "requirements.yaml").write_text(
                """id: ROOT
name: Visual fixture
type: FOLDER
children:
  - id: REQ-1
    name: Example heading
    type: ATOMIC
    description: Display one visible heading named Example.
    visual_reference: [./reference/only-listed.png, ./reference/missing.png]
""",
                encoding="utf-8",
            )
            (reference_dir / "only-listed.png").write_bytes(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9XPdUAAAAASUVORK5CYII="
                )
            )
            output = root / "output"
            with (
                patch.object(qualifier, "OpenAIChatClient", ScriptedModel),
                patch.dict(
                    os.environ,
                    {
                        "VISUAL_API_KEY": "fixture-only",
                        "VISUAL_BASE_URL": "https://vision.example.test/v1",
                        "VISUAL_MODEL": "fixture-vision",
                    },
                ),
            ):
                status = qualifier.main(
                    [str(requirement_dir), "--output-dir", str(output)]
                )
            self.assertEqual(status, 0)
            rows = [
                json.loads(line)
                for line in (output / ".arc" / "production-trace.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            batch = next(
                row for row in rows if row["event"] == "implementation_batch_started"
            )
            self.assertEqual(
                batch["payload"]["visual_references_available"],
                ["reference/only-listed.png"],
            )
            self.assertEqual(
                batch["payload"]["visual_references_unavailable"],
                ["reference/missing.png"],
            )
            first_prompt = next(
                row["payload"]["messages"][1]["content"]
                for row in rows if row["event"] == "model_request"
            )
            self.assertIn("not inspectable in this run", first_prompt)
            self.assertIn("reference/missing.png", first_prompt)
            self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])

    def test_shared_model_gateway_exposes_visual_reference_to_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirement_dir = root / "requirements"
            reference_dir = requirement_dir / "reference"
            reference_dir.mkdir(parents=True)
            (requirement_dir / "requirements.yaml").write_text(
                """id: ROOT
name: Visual fixture
type: FOLDER
children:
  - id: REQ-1
    name: Example heading
    type: ATOMIC
    description: Display one visible heading named Example.
    visual_reference: [./reference/only-listed.png]
""",
                encoding="utf-8",
            )
            (reference_dir / "only-listed.png").write_bytes(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9XPdUAAAAASUVORK5CYII="
                )
            )
            output = root / "output"
            with (
                patch.object(qualifier, "OpenAIChatClient", ScriptedModel),
                patch.dict(os.environ, {
                    "OPENAI_API_KEY": "shared-fixture-secret",
                    "OPENAI_BASE_URL": "https://gateway.example.test/v1",
                    "VISUAL_MODEL": "fixture-vision",
                }),
            ):
                status = qualifier.main([str(requirement_dir), "--output-dir", str(output)])
            self.assertEqual(status, 0)
            rows = [json.loads(line) for line in
                    (output / ".arc/production-trace.jsonl").read_text(encoding="utf-8").splitlines()]
            selected = next(row for row in rows if row["event"] == "visual_gateway_selected")
            self.assertEqual(selected["payload"]["source"], "shared-model-gateway")
            started = next(row for row in rows if row["event"] == "implementation_batch_started")
            self.assertEqual(started["payload"]["visual_references_available"],
                             ["reference/only-listed.png"])
            self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])

    def test_non_https_shared_visual_endpoint_does_not_abort_coding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirement_dir = root / "requirements"
            requirement_dir.mkdir()
            (requirement_dir / "requirements.yaml").write_text(
                """id: ROOT
name: Visual fixture
type: FOLDER
children:
  - id: REQ-1
    name: Example heading
    type: ATOMIC
    description: Display one visible heading named Example.
    visual_reference: [./reference/unavailable.png]
""",
                encoding="utf-8",
            )
            output = root / "output"
            with (
                patch.object(qualifier, "OpenAIChatClient", ScriptedModel),
                patch.dict(os.environ, {
                    "OPENAI_API_KEY": "shared-fixture-secret",
                    "OPENAI_BASE_URL": "http://host.docker.internal:19786/v1",
                    "VISUAL_MODEL": "fixture-vision",
                }),
            ):
                status = qualifier.main([str(requirement_dir), "--output-dir", str(output)])
            self.assertEqual(status, 0)
            rows = [json.loads(line) for line in
                    (output / ".arc/production-trace.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(any(row["event"] == "visual_gateway_unavailable" for row in rows))
            self.assertFalse(any(row["event"] == "visual_gateway_selected" for row in rows))
            started = next(row for row in rows if row["event"] == "implementation_batch_started")
            self.assertEqual(started["payload"]["visual_references_available"], [])
            self.assertEqual(
                started["payload"]["visual_references_unavailable"],
                ["reference/unavailable.png"],
            )


if __name__ == "__main__":
    unittest.main()
