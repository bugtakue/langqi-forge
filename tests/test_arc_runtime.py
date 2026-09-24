from __future__ import annotations

import importlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from factory26_harness.arc_runtime import ArcRuntime


class ArcRuntimeTests(unittest.TestCase):
    def test_failed_git_commit_can_be_followed_by_explicit_failed_state(self) -> None:
        sequence: list[str] = []

        def commit(_message: str) -> bool:
            sequence.append("commit_failed")
            return False

        sdk = SimpleNamespace(
            git=SimpleNamespace(commit=commit),
            events=SimpleNamespace(
                mark_implementation_done=lambda *_args: sequence.append("done"),
                mark_implementation_failed=lambda *_args: sequence.append("failed"),
            ),
        )
        runtime = ArcRuntime(sdk, Path("/unused"))
        with self.assertRaisesRegex(RuntimeError, "Git commit found no implementation changes"):
            runtime.finish_batch(1, ["REQ-1"])
        self.assertEqual(sequence, ["done", "commit_failed"])
        runtime.fail_batch(["REQ-1"], "commit failed")
        self.assertEqual(sequence, ["done", "commit_failed", "failed"])

    def test_successful_git_commit_includes_implementation_state(self) -> None:
        sequence: list[str] = []
        sdk = SimpleNamespace(
            git=SimpleNamespace(commit=lambda _message: sequence.append("commit") or True),
            events=SimpleNamespace(
                mark_implementation_done=lambda req_id, _message: sequence.append(req_id),
            ),
        )
        ArcRuntime(sdk, Path("/unused")).finish_batch(2, ["REQ-1", "REQ-2"])
        self.assertEqual(sequence, ["REQ-1", "REQ-2", "commit"])

    def test_missing_sdk_fails_closed_inside_runner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            missing = ModuleNotFoundError("No module named 'arcbench_agent_runtime'")
            missing.name = "arcbench_agent_runtime"
            with patch.dict(
                os.environ,
                {"ARCBENCH_RUNNER_EVENTS_PATH": str(output / ".arc/runner-events.jsonl")},
            ), patch("factory26_harness.arc_runtime.importlib.import_module", side_effect=missing):
                with self.assertRaisesRegex(RuntimeError, "SDK is unavailable"):
                    ArcRuntime.connect(output)

    def test_official_sdk_failed_commit_leaves_failed_requirement_and_run(self) -> None:
        try:
            importlib.import_module("arcbench_agent_runtime")
        except ModuleNotFoundError:
            self.skipTest("install submission requirements to exercise official SDK")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            arc_dir = output / ".arc"
            with patch.dict(
                os.environ,
                {
                    "ARCBENCH_RUNNER_EVENTS_PATH": str(arc_dir / "runner-events.jsonl"),
                    "ARCBENCH_TRACEABILITY_DIR": str(arc_dir / "traceability"),
                },
            ):
                runtime = ArcRuntime.connect(output)
                assert runtime is not None
                runtime.start(
                    {
                        "id": "ROOT",
                        "type": "FOLDER",
                        "children": [{"id": "REQ-1", "type": "ATOMIC"}],
                    }
                )
                (output / "frontend").mkdir()
                (output / "frontend" / "app.js").write_text("// baseline\n")
                runtime.commit_scaffold()
                runtime.begin_batch(["REQ-1"])
                (output / "frontend" / "app.js").write_text("// implementation\n")
                with patch.object(runtime.sdk.git, "commit", return_value=False):
                    with self.assertRaisesRegex(RuntimeError, "no implementation changes"):
                        runtime.finish_batch(1, ["REQ-1"])
                runtime.fail_batch(["REQ-1"], "commit failed")
                runtime.fail("commit failed")

            states = json.loads((arc_dir / "traceability/node_states.json").read_text())
            self.assertEqual(states["REQ-1"]["state"], "FAILED")
            events = [
                json.loads(line)
                for line in (arc_dir / "runner-events.jsonl").read_text().splitlines()
            ]
            self.assertEqual(
                [row["state"] for row in events if row.get("type") == "runner_state"],
                ["running", "failed"],
            )
            self.assertEqual(
                [row["status"] for row in events if row.get("type") == "requirement_state"],
                ["running", "completed", "failed"],
            )

    def test_official_sdk_writes_states_traceability_and_git_history(self) -> None:
        try:
            package = importlib.import_module("arcbench_agent_runtime")
        except ModuleNotFoundError:
            self.skipTest("install submission requirements to exercise official SDK")
        if not hasattr(package, "AgentRuntime"):
            self.skipTest("install submission requirements to exercise official SDK")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            arc_dir = output / ".arc"
            with patch.dict(
                os.environ,
                {
                    "ARCBENCH_RUNNER_EVENTS_PATH": str(arc_dir / "runner-events.jsonl"),
                    "ARCBENCH_TRACEABILITY_DIR": str(arc_dir / "traceability"),
                },
            ):
                runtime = ArcRuntime.connect(output)
                self.assertIsNotNone(runtime)
                runtime.start(
                    {
                        "id": "ROOT",
                        "name": "Neutral fixture",
                        "type": "FOLDER",
                        "children": [
                            {"id": "REQ-1", "name": "Example", "type": "ATOMIC"}
                        ],
                    }
                )
                (output / "frontend").mkdir()
                (output / "frontend" / "app.js").write_text("// neutral\n", encoding="utf-8")
                runtime.commit_scaffold()
                runtime.begin_batch(["REQ-1"])
                (output / "frontend" / "app.js").write_text("// implemented\n", encoding="utf-8")
                runtime.finish_batch(1, ["REQ-1"])
                runtime.complete()

            events = [
                json.loads(line)
                for line in (arc_dir / "runner-events.jsonl").read_text().splitlines()
            ]
            self.assertTrue(any(item.get("type") == "runner_state" and item.get("state") == "completed" for item in events))
            self.assertTrue(any(item.get("type") == "requirement_state" and item.get("status") == "completed" for item in events))
            self.assertFalse(any(item.get("phase") == "test" and item.get("status") == "passed" for item in events))
            requirements = json.loads((arc_dir / "traceability/requirements.json").read_text())
            node_states = json.loads((arc_dir / "traceability/node_states.json").read_text())
            self.assertIn("REQ-1", requirements)
            self.assertEqual(node_states["REQ-1"]["state"], "IMPLEMENTED")
            commits = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=output,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(commits.stdout.strip(), "2")
            status = subprocess.run(
                ["git", "status", "--short"],
                cwd=output,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(status.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
