from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class _PlannerHandler(BaseHTTPRequestHandler):
    calls = 0

    def log_message(self, *_args) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("content-length") or 0)
        request = json.loads(self.rfile.read(length))
        self.assert_planner_tool(request)
        type(self).calls += 1
        message = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "planner-1",
                    "type": "function",
                    "function": {
                        "name": "select_build_contract",
                        "arguments": json.dumps(
                            {
                                "domain": "github",
                                "kernel_eligible": True,
                                "capability_tags": ["repository_lifecycle"],
                                "risks": ["permission boundaries"],
                                "validation_focus": ["repository list persists"],
                                "rationale": "The GitHub kernel covers this contract.",
                            }
                        ),
                    },
                }
            ],
        }
        payload = {
            "id": "planner-fixture-response",
            "choices": [{"message": message}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30},
        }
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    @staticmethod
    def assert_planner_tool(request: dict) -> None:
        tools = request.get("tools") or []
        names = [item.get("function", {}).get("name") for item in tools]
        if "select_build_contract" not in names:
            raise AssertionError("planner tool schema was not sent")


class _WrongDomainPlannerHandler(_PlannerHandler):
    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("content-length") or 0)
        request = json.loads(self.rfile.read(length))
        self.assert_planner_tool(request)
        message = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "planner-wrong-domain",
                    "type": "function",
                    "function": {
                        "name": "select_build_contract",
                        "arguments": json.dumps(
                            {
                                "domain": "sheet",
                                "kernel_eligible": True,
                                "capability_tags": ["workbook_lifecycle"],
                                "risks": ["domain mismatch"],
                                "validation_focus": ["fail closed"],
                                "rationale": "Incorrectly selected the sheet kernel.",
                            }
                        ),
                    },
                }
            ],
        }
        self._send(message)

    def _send(self, message: dict) -> None:
        payload = {
            "id": "planner-wrong-domain-response",
            "choices": [{"message": message}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        }
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class _MalformedPlannerHandler(_PlannerHandler):
    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("content-length") or 0)
        request = json.loads(self.rfile.read(length))
        self.assert_planner_tool(request)
        message = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "planner-malformed",
                    "type": "function",
                    "function": {
                        "name": "select_build_contract",
                        "arguments": "not-json",
                    },
                }
            ],
        }
        payload = {
            "id": "planner-malformed-response",
            "choices": [{"message": message}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 5},
        }
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class DryRunIntegrationTests(unittest.TestCase):
    def _run_github_with_planner(self, handler: type[BaseHTTPRequestHandler]) -> dict:
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                temporary = Path(directory)
                requirements = temporary / "requirements"
                output = temporary / "output"
                requirements.mkdir()
                (requirements / "requirements.yaml").write_text(
                    """id: github-app
name: GitHub Code Collaboration
type: FOLDER
children:
  - id: repository-list
    name: List repositories
    type: ATOMIC
    description: A user can see repositories.
""",
                    encoding="utf-8",
                )
                environment = {
                    **os.environ,
                    "OPENAI_API_KEY": "planner-test",
                    "OPENAI_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1",
                    "MODEL": "planner-test-model",
                    "FACTORY26_MAX_MODEL_REQUESTS": "1",
                }
                command = [
                    sys.executable,
                    str(REPOSITORY_ROOT / "main.py"),
                    str(requirements),
                    "--output-dir",
                    str(output),
                    "--web-port",
                    "3992",
                    "--smoke-port",
                    "3993",
                    "--strict-exit",
                ]
                completed = subprocess.run(
                    command,
                    cwd=REPOSITORY_ROOT,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
                self.assertEqual(
                    completed.returncode, 0, completed.stdout + "\n" + completed.stderr
                )
                return json.loads(
                    (output / ".arc" / "harness-report.json").read_text(
                        encoding="utf-8"
                    )
                )
        finally:
            server.shutdown()
            server.server_close()

    def test_contract_build_start_health_and_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            requirements = temporary / "requirements"
            output = temporary / "output"
            requirements.mkdir()
            (requirements / "requirements.yaml").write_text(
                """id: app
name: Demo application
type: FOLDER
children:
  - id: item-create
    name: Create an item
    type: ATOMIC
    description: A user can enter a name and save an item.
    scenarios:
      - id: create-success
        name: Save a valid item
        steps:
          - keyword: Given
            content: the application is open
          - keyword: When
            content: the user enters a name and selects Save
          - keyword: Then
            content: the item remains after refresh
""",
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(REPOSITORY_ROOT / "main.py"),
                str(requirements),
                "--output-dir",
                str(output),
                "--web-port",
                "3988",
                "--smoke-port",
                "3989",
                "--dry-run",
                "--strict-exit",
            ]
            completed = subprocess.run(
                command,
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            self.assertEqual(
                completed.returncode, 0, completed.stdout + "\n" + completed.stderr
            )
            self.assertTrue((output / "frontend" / "dist" / "index.html").is_file())
            self.assertTrue((output / "backend" / "server.mjs").is_file())
            report = json.loads(
                (output / ".arc" / "harness-report.json").read_text(encoding="utf-8")
            )
            self.assertTrue(report["all_local_checks_passed"])
            self.assertEqual(report["requirement_count"], 1)
            events = (output / ".arc" / "runner-events.jsonl").read_text(
                encoding="utf-8"
            )
            self.assertIn('"state": "completed"', events)
            self.assertTrue(
                (output / ".arc" / "traceability" / "requirements.json").is_file()
            )
            contract_tests = json.loads(
                (output / ".arc" / "traceability" / "tests.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(len(contract_tests), 1)
            self.assertIsNone(next(iter(contract_tests.values()))["passed"])
            log = subprocess.run(
                ["git", "log", "--oneline"],
                cwd=output,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.splitlines()
            self.assertGreaterEqual(len(log), 2)

    def test_sheet_domain_uses_full_template(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            requirements = temporary / "requirements"
            output = temporary / "output"
            requirements.mkdir()
            (requirements / "requirements.yaml").write_text(
                """id: sheet-app
name: Online Spreadsheet Data Workspace
type: FOLDER
children:
  - id: edit-cell
    name: Edit a spreadsheet cell
    type: ATOMIC
    description: A user can edit a cell and keep the value after refresh.
""",
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(REPOSITORY_ROOT / "main.py"),
                str(requirements),
                "--output-dir",
                str(output),
                "--web-port",
                "3990",
                "--smoke-port",
                "3991",
                "--dry-run",
                "--strict-exit",
            ]
            completed = subprocess.run(
                command,
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            self.assertEqual(
                completed.returncode, 0, completed.stdout + "\n" + completed.stderr
            )
            frontend = (output / "frontend" / "src" / "app.js").read_text(
                encoding="utf-8"
            )
            backend = (output / "backend" / "server.mjs").read_text(encoding="utf-8")
            self.assertIn("Pivot table editor", frontend)
            self.assertIn("/api/workbooks", backend)
            plan = json.loads(
                (output / ".arc" / "compiled-plan.json").read_text(encoding="utf-8")
            )
            self.assertEqual(plan["detected_domain"], "sheet")
            report = json.loads(
                (output / ".arc" / "harness-report.json").read_text(encoding="utf-8")
            )
            self.assertTrue(report["all_local_checks_passed"])

    def test_stable_domain_uses_one_planner_call_without_coding_turns(self) -> None:
        _PlannerHandler.calls = 0
        server = ThreadingHTTPServer(("127.0.0.1", 0), _PlannerHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                temporary = Path(directory)
                requirements = temporary / "requirements"
                output = temporary / "output"
                requirements.mkdir()
                (requirements / "requirements.yaml").write_text(
                    """id: github-app
name: GitHub Code Collaboration
type: FOLDER
children:
  - id: repository-list
    name: List repositories
    type: ATOMIC
    description: A user can see repositories.
""",
                    encoding="utf-8",
                )
                environment = {
                    **os.environ,
                    "OPENAI_API_KEY": "planner-test",
                    "OPENAI_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1",
                    "MODEL": "planner-test-model",
                }
                command = [
                    sys.executable,
                    str(REPOSITORY_ROOT / "main.py"),
                    str(requirements),
                    "--output-dir",
                    str(output),
                    "--web-port",
                    "3992",
                    "--smoke-port",
                    "3993",
                    "--strict-exit",
                ]
                completed = subprocess.run(
                    command,
                    cwd=REPOSITORY_ROOT,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
                self.assertEqual(
                    completed.returncode, 0, completed.stdout + "\n" + completed.stderr
                )
                report = json.loads(
                    (output / ".arc" / "harness-report.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertFalse(report["dry_run"])
                self.assertTrue(report["run_id"])
                self.assertIn("revision", report["source_identity"])
                self.assertEqual(
                    report["execution_route"], "planner-approved-deterministic-kernel"
                )
                self.assertEqual(report["planner_status"], "completed")
                self.assertEqual(report["agent_iterations"], 1)
                self.assertEqual(report["coding_agent_iterations"], 0)
                self.assertEqual(
                    report["model_usage"],
                    {
                        "prompt_tokens": 120,
                        "completion_tokens": 30,
                        "request_count": 1,
                        "http_attempt_count": 1,
                    },
                )
                self.assertEqual(
                    report["model_gateway"]["provenance"],
                    "local-openai-protocol-fixture",
                )
                self.assertEqual(_PlannerHandler.calls, 1)
                trace = (output / ".arc" / "production-trace.jsonl").read_text(
                    encoding="utf-8"
                )
                self.assertIn('"event": "agent_tool_call"', trace)
                self.assertIn('"prompt_invoked": true', trace)
        finally:
            server.shutdown()
            server.server_close()

    def test_planner_domain_disagreement_keeps_available_kernel_but_fails_release_route(
        self,
    ) -> None:
        report = self._run_github_with_planner(_WrongDomainPlannerHandler)
        self.assertTrue(report["run_completed_successfully"])
        self.assertEqual(
            report["execution_route"],
            "planner-disagreement-safe-deterministic-kernel",
        )
        self.assertEqual(report["planner_contract"]["domain"], "sheet")

    def test_malformed_planner_contract_uses_available_kernel_but_fails_release_route(
        self,
    ) -> None:
        report = self._run_github_with_planner(_MalformedPlannerHandler)
        self.assertTrue(report["run_completed_successfully"])
        self.assertEqual(report["planner_status"], "failed-after-retries")
        self.assertEqual(
            report["execution_route"],
            "planner-failure-safe-deterministic-kernel",
        )


if __name__ == "__main__":
    unittest.main()
