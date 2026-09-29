from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory26_harness import qualifier
from factory26_harness.agent import AgentRun
from factory26_harness.agent_first_fallback import AgentFirstFallbackGraph
from factory26_harness.checks import CheckResult


class _TraceFixture:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def record(self, event: str, **payload) -> None:
        self.events.append((event, payload))


class _ModelFixture:
    def __init__(self, trace, *, planned_turns=None) -> None:
        self.trace = trace
        self.planned_turns = planned_turns
        self.request_count = 0
        self.max_requests = None
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.http_attempt_count = 0

    def gateway_evidence(self) -> dict[str, str]:
        return {"provenance": "agent-first-fallback-test", "model": "fixture"}

    def budget_evidence(self) -> dict[str, int | None]:
        return {"planned_turns": self.planned_turns, "max_requests": None}


class _FailingAgent:
    def __init__(self, model, tools, _trace, max_turns=20) -> None:
        self.model = model
        self.tools = tools

    def implement(self, nodes, related_files=(), *, task_outline="", accepted_ids=()):
        self.model.request_count += 1
        return AgentRun(False, "fixture Agent failed before acceptance", (), 1)


class AgentFirstFallbackTests(unittest.TestCase):
    def test_graph_accepts_one_fallback_and_rejects_a_third_attempt(self) -> None:
        trace = _TraceFixture()
        graph = AgentFirstFallbackGraph(
            run_id="run-1",
            requirement_sha256="req-sha",
            requirement_ids=["REQ-1-1-1"],
            tree={"name": "GitHub Collaboration Platform Core Requirements"},
            trace=trace,
        )

        graph.begin_batch(["REQ-1-1-1"])
        graph.agent_result(False, "model failed")
        binding = graph.start_fallback()
        self.assertEqual(binding.name, "github-canvas")
        graph.finish_fallback(
            passed=True,
            covered_ids=["REQ-1-1-1"],
            source_sha256="app-sha",
            summary="fallback accepted",
        )

        self.assertTrue(graph.fallback_recovered)
        self.assertEqual(graph.context.state, "TERMINAL")
        self.assertEqual(graph.context.completed_ids, ["REQ-1-1-1"])
        with self.assertRaises(RuntimeError):
            graph.start_fallback()
        self.assertTrue(any(event == "harness_fallback_finished" for event, _ in trace.events))

    def test_main_runs_agent_once_then_uses_verified_github_fallback(self) -> None:
        passing_check = CheckResult("fixture", True, "fixture passed", (), 0.0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirements = root / "requirements"
            requirements.mkdir()
            (requirements / "requirements.yaml").write_text(
                "id: ROOT\n"
                "name: GitHub Collaboration Platform Core Requirements\n"
                "type: FOLDER\n"
                "children:\n"
                "  - id: REQ-1-1-1\n"
                "    name: Register a New GitHub Account\n"
                "    type: ATOMIC\n"
                "    description: Register a new account.\n",
                encoding="utf-8",
            )
            output = root / "output"
            with (
                patch.object(qualifier, "OpenAIChatClient", _ModelFixture),
                patch.object(qualifier, "CodingAgent", _FailingAgent),
                patch.object(qualifier, "run_full_checks", return_value=[passing_check]),
            ):
                status = qualifier.main(
                    [
                        str(requirements),
                        "--output-dir",
                        str(output),
                        "--batch-size",
                        "1",
                        "--salvage-splits",
                        "0",
                        "--repair-rounds",
                        "2",
                        "--agent-first-fallback",
                    ]
                )

            self.assertEqual(status, 0)
            report = json.loads((output / ".arc/harness-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["harness_mode"], "agent-first-with-one-deterministic-fallback")
            self.assertTrue(report["fallback_recovered"])
            self.assertTrue(report["agent_first_fallback"]["fallback_attempted"])
            self.assertEqual(report["model_requests"], 1)
            self.assertEqual(report["implemented_requirements"], ["REQ-1-1-1"])
            plan = json.loads((output / ".arc/compiled-plan.json").read_text(encoding="utf-8"))
            self.assertTrue(plan["task_specific_prebuilt_code"])
            self.assertTrue(plan["agent_first_fallback"])
            self.assertIn(
                "register-form",
                (output / "frontend/src/app.js").read_text(encoding="utf-8"),
            )

    def test_passed_agent_still_recovers_the_covered_github_canvas_once(self) -> None:
        class PassingAgent:
            calls = 0

            def __init__(self, model, tools, _trace, max_turns=20) -> None:
                self.model = model
                type(self).calls += 1

            def implement(self, nodes, related_files=(), *, task_outline="", accepted_ids=()):
                self.model.request_count += 2
                return AgentRun(True, "AUDIT PASS: local checks only", ("frontend/src/app.js",), 2)

        passing_check = CheckResult("fixture", True, "fixture passed", (), 0.0)
        PassingAgent.calls = 0
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirements = root / "requirements"
            requirements.mkdir()
            (requirements / "requirements.yaml").write_text(
                "id: ROOT\n"
                "name: GitHub Collaboration Platform Core Requirements\n"
                "type: FOLDER\n"
                "children:\n"
                "  - id: REQ-1-1-1\n"
                "    name: Register\n"
                "    type: ATOMIC\n"
                "    description: Register.\n"
                "  - id: REQ-1-1-2\n"
                "    name: Sign in\n"
                "    type: ATOMIC\n"
                "    description: Sign in.\n",
                encoding="utf-8",
            )
            output = root / "output"
            with (
                patch.object(qualifier, "OpenAIChatClient", _ModelFixture),
                patch.object(qualifier, "CodingAgent", PassingAgent),
                patch.object(qualifier, "run_full_checks", return_value=[passing_check]),
            ):
                status = qualifier.main(
                    [
                        str(requirements),
                        "--output-dir",
                        str(output),
                        "--batch-size",
                        "1",
                        "--agent-first-fallback",
                    ]
                )
            self.assertEqual(status, 0)
            self.assertEqual(PassingAgent.calls, 1)
            report = json.loads((output / ".arc/harness-report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["fallback_recovered"])
            self.assertEqual(report["model_requests"], 2)
            self.assertEqual(report["implemented_requirements"], ["REQ-1-1-1", "REQ-1-1-2"])
            self.assertIn(
                "register-form",
                (output / "frontend/src/app.js").read_text(encoding="utf-8"),
            )

    def test_submitted_entry_names_one_recovery_after_the_model(self) -> None:
        entry = Path(__file__).resolve().parents[1] / "main.py"
        text = entry.read_text(encoding="utf-8")
        self.assertIn('os.environ.setdefault("FACTORY26_AGENT_FIRST_FALLBACK", "1")', text)
        self.assertIn('os.environ.setdefault("FACTORY26_MAX_AGENT_TURNS", "8")', text)
        self.assertLess(
            text.index("FACTORY26_AGENT_FIRST_FALLBACK"),
            text.index("raise SystemExit(main())"),
        )

    def test_recovered_public_canvases_pass_real_startup_checks(self) -> None:
        from deterministic import github_canvas, sheet_canvas
        from factory26_harness.checks import run_full_checks
        from factory26_harness.generic_scaffold import scaffold_workspace
        from factory26_harness.requirements import load_requirement_tree

        project = Path(__file__).resolve().parents[1]
        cases = (
            (
                "github",
                github_canvas,
                project / "docs/evidence/conductor-20260928/canvas-public-source/hackathon--github",
                4321,
            ),
            (
                "sheet",
                sheet_canvas,
                project / "docs/evidence/sheet-requirements-20260929.yaml",
                4322,
            ),
        )
        for label, module, path, port in cases:
            with self.subTest(label=label):
                tree = load_requirement_tree(path)
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    scaffold_workspace(root)
                    self.assertTrue(module.apply_if_matched(root, tree))
                    failed = [item.name for item in run_full_checks(root, port) if not item.passed]
                self.assertEqual(failed, [])


if __name__ == "__main__":
    unittest.main()
