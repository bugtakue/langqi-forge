from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from email.utils import format_datetime
from http.client import RemoteDisconnected
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from factory26_harness.agent import CodingAgent, _compact_tool_result
from factory26_harness.model import (
    ModelBudgetExceeded,
    OpenAIChatClient,
    _retry_after_seconds,
)
from factory26_harness.requirements import RequirementNode
from factory26_harness.trace import ProductionTrace
from factory26_harness.workspace_tools import WorkspaceTools


DUMMY_BUILD = (
    'node -e "require(\'fs\').mkdirSync(\'dist\',{recursive:true});'
    'require(\'fs\').writeFileSync(\'dist/index.html\',\'<html></html>\')"'
)


class _ModelHandler(BaseHTTPRequestHandler):
    calls = 0
    payloads: list[dict] = []
    audit_mode = "pass"

    def log_message(self, *_args) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("content-length") or 0)
        type(self).payloads.append(json.loads(self.rfile.read(length)))
        type(self).calls += 1
        if type(self).calls == 1:
            message = {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "write_file",
                            "arguments": json.dumps(
                                {
                                    "path": "frontend/src/generated.txt",
                                    "content": "generated\n",
                                }
                            ),
                        },
                    }
                ],
            }
        elif type(self).calls == 2:
            message = {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-2",
                        "type": "function",
                        "function": {
                            "name": "run_validation",
                            "arguments": json.dumps({"scope": "quick"}),
                        },
                    }
                ],
            }
        elif type(self).audit_mode == "revalidate":
            message = {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-audit-validation",
                        "type": "function",
                        "function": {
                            "name": "run_validation",
                            "arguments": json.dumps({"scope": "quick"}),
                        },
                    }
                ],
            }
        else:
            message = {
                "role": "assistant",
                "content": (
                    "AUDIT BLOCKED: fixture does not cover the requirement"
                    if type(self).audit_mode == "blocked"
                    else "AUDIT PASS: fixture validated; browser behavior unverified"
                ),
            }
        payload = {
            "choices": [{"message": message}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class _StatusHandler(BaseHTTPRequestHandler):
    calls = 0
    responses: list[tuple[int, str | None, bytes]] = []

    def log_message(self, *_args) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        self.rfile.read(int(self.headers.get("content-length") or 0))
        index = type(self).calls
        type(self).calls += 1
        status, retry_after, content = type(self).responses[index]
        self.send_response(status)
        if retry_after is not None:
            self.send_header("Retry-After", retry_after)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


class ModelLoopTests(unittest.TestCase):
    def test_repeated_no_tool_summaries_stop_before_spending_full_budget(self) -> None:
        class EmptyModel:
            calls = 0

            def complete(self, _messages, _tools):
                self.calls += 1
                return SimpleNamespace(
                    raw_message={"role": "assistant", "content": "I cannot proceed yet."},
                    tool_calls=(),
                    content="I cannot proceed yet.",
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = ProductionTrace(root / ".arc/trace.jsonl")
            model = EmptyModel()
            node = RequirementNode(
                req_id="R-EMPTY",
                name="No-op fixture",
                description="Implement a real change.",
                dependencies=(),
                scenarios=(),
                visual_reference=(),
                raw={},
            )
            result = CodingAgent(
                model, WorkspaceTools(root, trace, 3926), trace, max_turns=20
            ).implement([node])
            self.assertFalse(result.completed)
            self.assertEqual(model.calls, 3)
            self.assertEqual(result.turns, 3)
            rows = [json.loads(line) for line in trace.path.read_text().splitlines()]
            self.assertEqual(rows[-1]["event"], "agent_session_stalled")
            self.assertIn("no-tool", rows[-1]["payload"]["reason"])

    def test_next_batch_prompt_names_prior_generated_modules_without_trusting_them(self) -> None:
        class CaptureModel:
            def __init__(self) -> None:
                self.prompts: list[str] = []

            def complete(self, messages, _tools):
                self.prompts.append(messages[1]["content"])
                return SimpleNamespace(
                    raw_message={"role": "assistant", "content": ""},
                    tool_calls=(),
                    content="",
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = ProductionTrace(root / ".arc" / "trace.jsonl")
            model = CaptureModel()
            node = RequirementNode(
                req_id="R2",
                name="Use prior module",
                description="Extend the existing feature.",
                dependencies=(),
                scenarios=(),
                visual_reference=(),
                raw={},
            )
            CodingAgent(model, WorkspaceTools(root, trace, 3927), trace, max_turns=2).implement(
                [node],
                related_files=[
                    "backend/routes/notes.mjs",
                    "frontend/src/<do-not-obey>.js",
                ],
                task_outline='{"root_name":"Example","requirements":[{"id":"R2","name":"Current"},{"id":"R3","name":"Later"}]}',
            )
            first_prompt = model.prompts[0]
            self.assertIn("<untrusted_task_outline>", first_prompt)
            self.assertIn('"id":"R3"', first_prompt)
            self.assertNotIn("[R3]", first_prompt)
            self.assertIn("[R2] Use prior module", first_prompt)
            self.assertIn("backend/routes/notes.mjs", first_prompt)
            self.assertIn("frontend/src/\\u003cdo-not-obey>.js", first_prompt)
            self.assertIn("<untrusted_prior_source_paths>", first_prompt)

    def test_retry_after_http_date_is_interpreted_as_a_bounded_delay(self) -> None:
        now = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)
        deadline = datetime(2026, 9, 25, 12, 0, 7, tzinfo=timezone.utc)
        with patch("factory26_harness.model.datetime") as clock:
            clock.now.return_value = now
            delay = _retry_after_seconds(
                {"retry-after": format_datetime(deadline, usegmt=True)}
            )
        self.assertEqual(delay, 7)

    def _run_status_sequence(
        self,
        responses: list[tuple[int, str | None, bytes]],
        *,
        retry_cap: int = 60,
    ) -> tuple[OpenAIChatClient, list[dict], list[int], str | None]:
        _StatusHandler.calls = 0
        _StatusHandler.responses = responses
        server = ThreadingHTTPServer(("127.0.0.1", 0), _StatusHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                trace = ProductionTrace(Path(directory) / "trace.jsonl")
                environment = {
                    "OPENAI_API_KEY": "test-secret",
                    "OPENAI_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1",
                    "MODEL": "mock-model",
                    "FACTORY26_MAX_RETRY_AFTER_SECONDS": str(retry_cap),
                }
                with (
                    patch.dict(os.environ, environment, clear=True),
                    patch("factory26_harness.model.time.sleep") as sleep,
                ):
                    client = OpenAIChatClient(trace)
                    error = None
                    try:
                        client.complete([{"role": "user", "content": "test"}], [])
                    except RuntimeError as exc:
                        error = str(exc)
                rows = [
                    json.loads(line)
                    for line in trace.path.read_text(encoding="utf-8").splitlines()
                ]
                return client, rows, [call.args[0] for call in sleep.call_args_list], error
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

    def test_transient_http_failures_honor_retry_after_and_recover(self) -> None:
        success = json.dumps(
            {"choices": [{"message": {"role": "assistant", "content": "done"}}]}
        ).encode("utf-8")
        client, rows, sleeps, error = self._run_status_sequence(
            [(429, "3", b"busy"), (503, None, b"unavailable"), (200, None, success)]
        )
        self.assertIsNone(error)
        self.assertEqual(client.http_attempt_count, 3)
        self.assertEqual(client.request_count, 1)
        self.assertEqual(sleeps, [3, 2])
        failures = [row["payload"] for row in rows if row["event"] == "model_error"]
        self.assertEqual([row["http_status"] for row in failures], [429, 503])
        self.assertTrue(all(row["will_retry"] for row in failures))

    def test_authentication_failure_does_not_retry_or_log_provider_body(self) -> None:
        private_body = b"invalid key: nonstandard-private-test-value"
        client, rows, sleeps, error = self._run_status_sequence(
            [(401, "1", private_body)]
        )
        self.assertEqual(error, "attempt 1: HTTP 401")
        self.assertEqual(client.http_attempt_count, 1)
        self.assertEqual(client.request_count, 0)
        self.assertEqual(sleeps, [])
        self.assertNotIn(private_body.decode("utf-8"), json.dumps(rows))
        failure = next(row["payload"] for row in rows if row["event"] == "model_error")
        self.assertFalse(failure["retryable"])
        self.assertFalse(failure["will_retry"])

    def test_long_retry_after_fails_closed_without_early_retry(self) -> None:
        client, rows, sleeps, error = self._run_status_sequence(
            [(429, "90", b"wait")], retry_cap=60
        )
        self.assertEqual(error, "attempt 1: HTTP 429 (Retry-After exceeds local cap)")
        self.assertEqual(client.http_attempt_count, 1)
        self.assertEqual(sleeps, [])
        failure = next(row["payload"] for row in rows if row["event"] == "model_error")
        self.assertTrue(failure["retry_after_exceeds_limit"])
        self.assertFalse(failure["will_retry"])

    def test_malformed_success_response_is_not_billed_as_a_second_request(self) -> None:
        client, rows, sleeps, error = self._run_status_sequence(
            [(200, None, b'{"choices":[]}')]
        )
        self.assertEqual(error, "invalid model response")
        self.assertEqual(client.http_attempt_count, 1)
        self.assertEqual(client.request_count, 0)
        self.assertEqual(sleeps, [])
        failure = next(row["payload"] for row in rows if row["event"] == "model_error")
        self.assertFalse(failure["will_retry"])

    def test_browser_probe_tool_summary_keeps_bounded_behavioral_evidence(self) -> None:
        summary = _compact_tool_result(
            "browser_probe",
            {
                "ok": False,
                "behavioral_checks": 2,
                "behavioral_assertions": 3,
                "assertion_failures": [
                    {"step": 1, "missing": ["Saved"], "unexpected": []},
                    {"step": 2, "missing": [], "unexpected": ["Error"]},
                    {"step": 3, "missing": ["Other"], "unexpected": []},
                ],
                "page_errors": ["TypeError", "ReferenceError", "ExtraError"],
                "blocked_external_hosts": ["example.com"],
            },
        )
        self.assertEqual(summary["behavioral_checks"], 2)
        self.assertEqual(summary["behavioral_assertions"], 3)
        self.assertEqual(len(summary["assertion_failures"]), 2)
        self.assertEqual(summary["page_errors"], ["TypeError", "ReferenceError"])

    def test_workload_budget_scales_to_multi_batch_public_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            trace = ProductionTrace(Path(directory) / "trace.jsonl")
            credentials = {
                "OPENAI_API_KEY": "test-secret",
                "OPENAI_BASE_URL": "https://gateway.example.test/v1",
                "MODEL": "mock-model",
            }
            with patch.dict(os.environ, credentials, clear=True):
                client = OpenAIChatClient(trace, planned_turns=380)
                self.assertEqual(client.budget_evidence(), {
                    "planned_turns": 380,
                    "max_requests": 380,
                    "max_prompt_tokens": 2_280_000,
                    "max_completion_tokens": 950_000,
                    "max_retry_after_seconds": 60,
                })
            with patch.dict(
                os.environ,
                {
                    **credentials,
                    "FACTORY26_MAX_MODEL_REQUESTS": "72",
                    "FACTORY26_MAX_TOTAL_PROMPT_TOKENS": "1000",
                    "FACTORY26_MAX_TOTAL_COMPLETION_TOKENS": "500",
                },
                clear=True,
            ):
                client = OpenAIChatClient(trace, planned_turns=380)
                self.assertEqual(client.max_requests, 72)
                self.assertEqual(client.max_total_prompt_tokens, 1000)
                self.assertEqual(client.max_total_completion_tokens, 500)

    def test_local_token_budget_failure_is_not_retried(self) -> None:
        class FakeResponse:
            headers: dict[str, str] = {}

            def __enter__(self):
                return self

            def __exit__(self, *_args) -> None:
                return None

            @staticmethod
            def read(_limit: int) -> bytes:
                return json.dumps(
                    {
                        "choices": [
                            {"message": {"role": "assistant", "content": "done"}}
                        ],
                        "usage": {"prompt_tokens": 2, "completion_tokens": 1},
                    }
                ).encode("utf-8")

        with tempfile.TemporaryDirectory() as directory:
            trace = ProductionTrace(Path(directory) / "trace.jsonl")
            environment = {
                "OPENAI_API_KEY": "test-secret",
                "OPENAI_BASE_URL": "https://gateway.example.test/v1",
                "MODEL": "mock-model",
                "FACTORY26_MAX_TOTAL_PROMPT_TOKENS": "1",
            }
            with (
                patch.dict(os.environ, environment, clear=False),
                patch(
                    "factory26_harness.model.urllib.request.urlopen",
                    return_value=FakeResponse(),
                ) as request,
            ):
                client = OpenAIChatClient(trace)
                with self.assertRaises(ModelBudgetExceeded):
                    client.complete([{"role": "user", "content": "test"}], [])
            self.assertEqual(request.call_count, 1)
            self.assertEqual(client.http_attempt_count, 1)
            self.assertEqual(client.request_count, 1)
            self.assertEqual(client.total_prompt_tokens, 2)
            self.assertEqual(client.total_completion_tokens, 1)
            events = [
                json.loads(line)["event"]
                for line in (Path(directory) / "trace.jsonl").read_text().splitlines()
            ]
            self.assertIn("model_response", events)
            self.assertIn("model_budget_exhausted", events)

    def test_remote_disconnect_is_retried_within_the_bounded_http_policy(self) -> None:
        class FakeResponse:
            headers: dict[str, str] = {}

            def __enter__(self):
                return self

            def __exit__(self, *_args) -> None:
                return None

            @staticmethod
            def read(_limit: int) -> bytes:
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": "recovered",
                                }
                            }
                        ],
                        "usage": {"prompt_tokens": 3, "completion_tokens": 1},
                    }
                ).encode("utf-8")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = ProductionTrace(root / "trace.jsonl")
            environment = {
                "OPENAI_API_KEY": "test-secret",
                "OPENAI_BASE_URL": "https://gateway.example.test/v1",
                "MODEL": "mock-model",
            }
            with (
                patch.dict(os.environ, environment, clear=False),
                patch(
                    "factory26_harness.model.urllib.request.urlopen",
                    side_effect=[RemoteDisconnected("closed"), FakeResponse()],
                ),
                patch("factory26_harness.model.time.sleep"),
            ):
                client = OpenAIChatClient(trace)
                reply = client.complete(
                    [{"role": "user", "content": "test"}],
                    [],
                    max_attempts=2,
                )

            self.assertEqual(reply.content, "recovered")
            self.assertEqual(client.request_count, 1)
            self.assertEqual(client.http_attempt_count, 2)
            rows = [
                json.loads(line)
                for line in trace.path.read_text(encoding="utf-8").splitlines()
            ]
            errors = [row for row in rows if row["event"] == "model_error"]
            self.assertEqual(len(errors), 1)
            self.assertEqual(
                errors[0]["payload"]["error_type"], "RemoteDisconnected"
            )

    def test_openai_tool_loop_edits_workspace_and_tracks_usage(self) -> None:
        _ModelHandler.calls = 0
        _ModelHandler.payloads = []
        _ModelHandler.audit_mode = "pass"
        server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "frontend").mkdir()
                (root / "backend").mkdir()
                (root / "frontend" / "package.json").write_text(
                    json.dumps(
                        {
                            "name": "test-frontend",
                            "private": True,
                            "scripts": {"build": DUMMY_BUILD},
                        }
                    ),
                    encoding="utf-8",
                )
                (root / "backend" / "package.json").write_text(
                    json.dumps(
                        {
                            "name": "test-backend",
                            "private": True,
                            "scripts": {"start": 'node -e ""'},
                        }
                    ),
                    encoding="utf-8",
                )
                trace = ProductionTrace(root / ".arc" / "trace.jsonl")
                environment = {
                    "OPENAI_API_KEY": "test-secret",
                    "OPENAI_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1",
                    "MODEL": "mock-model",
                }
                with patch.dict(os.environ, environment, clear=False):
                    client = OpenAIChatClient(trace)
                    tools = WorkspaceTools(root, trace, smoke_port=3921)
                    node = RequirementNode(
                        req_id="R1",
                        name="Generate a file",
                        description="Create one implementation file.",
                        dependencies=(),
                        scenarios=(),
                        visual_reference=(),
                        raw={},
                    )
                    result = CodingAgent(client, tools, trace, max_turns=4).implement(
                        [node]
                    )
                self.assertTrue(result.completed)
                self.assertEqual(
                    (root / "frontend" / "src" / "generated.txt").read_text(),
                    "generated\n",
                )
                self.assertEqual(client.total_prompt_tokens, 30)
                self.assertEqual(client.total_completion_tokens, 15)
                self.assertEqual(result.turns, 3)
                first_messages = _ModelHandler.payloads[0]["messages"]
                self.assertIn("read_files", first_messages[0]["content"])
                self.assertIn("at most 4 model turns", first_messages[1]["content"])
                second_messages = _ModelHandler.payloads[1]["messages"]
                self.assertTrue(
                    any(
                        message.get("role") == "user"
                        and "Turn-budget checkpoint: 3 model turns remain"
                        in message.get("content", "")
                        for message in second_messages
                    )
                )
                final_messages = _ModelHandler.payloads[-1]["messages"]
                self.assertTrue(
                    any(
                        message.get("role") == "user"
                        and "requirement-by-requirement audit"
                        in message.get("content", "")
                        and "<untrusted_changed_sources>" in message.get("content", "")
                        and "frontend/src/generated.txt" in message.get("content", "")
                        and "generated" in message.get("content", "")
                        for message in final_messages
                    )
                )
                trace_rows = [
                    json.loads(line)
                    for line in (root / ".arc" / "trace.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ]
                completions = [
                    row
                    for row in trace_rows
                    if row["event"] == "agent_session_completed"
                ]
                audit_requests = [
                    row
                    for row in trace_rows
                    if row["event"] == "agent_acceptance_audit_requested"
                ]
                self.assertEqual(
                    audit_requests[-1]["payload"].get("trigger"),
                    "first_passing_implementation_validation",
                )
                self.assertEqual(
                    completions[-1]["payload"]["summary"],
                    "AUDIT PASS: fixture validated; browser behavior unverified",
                )
                self.assertTrue(
                    completions[-1]["payload"]["acceptance_audit_self_reported"]
                )
                self.assertNotIn("completed_on_validation", completions[-1]["payload"])
                self.assertNotIn(
                    "test-secret",
                    (root / ".arc" / "trace.jsonl").read_text(encoding="utf-8"),
                )
        finally:
            server.shutdown()
            server.server_close()

    def test_revalidation_or_blocked_audit_cannot_complete_implementation(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for mode in ("revalidate", "blocked"):
                with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                    _ModelHandler.calls = 0
                    _ModelHandler.audit_mode = mode
                    root = Path(directory)
                    for component, scripts in (
                        ("frontend", {"build": DUMMY_BUILD}),
                        ("backend", {"start": 'node -e ""'}),
                    ):
                        (root / component).mkdir()
                        (root / component / "package.json").write_text(
                            json.dumps({"name": component, "private": True, "scripts": scripts}),
                            encoding="utf-8",
                        )
                    trace = ProductionTrace(root / ".arc" / "trace.jsonl")
                    with patch.dict(
                        os.environ,
                        {
                            "OPENAI_API_KEY": "test-secret",
                            "OPENAI_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1",
                            "MODEL": "mock-model",
                        },
                        clear=False,
                    ):
                        model = OpenAIChatClient(trace)
                        tools = WorkspaceTools(root, trace, smoke_port=3923)
                        node = RequirementNode(
                            req_id="R1",
                            name="Generate a file",
                            description="Create one implementation file.",
                            dependencies=(),
                            scenarios=(),
                            visual_reference=(),
                            raw={},
                        )
                        result = CodingAgent(model, tools, trace, max_turns=4).implement([node])
                    self.assertFalse(result.completed)
                    self.assertEqual(result.turns, 3 if mode == "blocked" else 4)
                    self.assertTrue(tools.current_changes_validated)
                    events = [
                        json.loads(line)["event"]
                        for line in trace.path.read_text(encoding="utf-8").splitlines()
                    ]
                    self.assertIn(
                        "agent_session_stalled" if mode == "blocked" else "agent_session_exhausted",
                        events,
                    )
                    self.assertNotIn("agent_session_completed", events)
        finally:
            _ModelHandler.audit_mode = "pass"
            server.shutdown()
            server.server_close()

    def test_tool_call_flood_is_stopped_before_any_workspace_action(self) -> None:
        class FloodModel:
            def complete(self, _messages, _tools):
                calls = tuple(
                    {
                        "id": f"call-{index}",
                        "type": "function",
                        "function": {
                            "name": "list_files",
                            "arguments": "{}",
                        },
                    }
                    for index in range(9)
                )
                return SimpleNamespace(
                    tool_calls=calls,
                    raw_message={"role": "assistant", "tool_calls": calls},
                    content="",
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "frontend").mkdir()
            (root / "backend").mkdir()
            trace = ProductionTrace(root / ".trace" / "trace.jsonl")
            tools = WorkspaceTools(root, trace, smoke_port=3922)
            requirement = RequirementNode(
                req_id="R-FLOOD",
                name="Bound tool execution",
                description="A normal requirement.",
                dependencies=(),
                scenarios=(),
                visual_reference=(),
                raw={},
            )
            result = CodingAgent(FloodModel(), tools, trace, max_turns=3).implement(
                [requirement]
            )
            self.assertFalse(result.completed)
            self.assertEqual(result.summary, "workspace tool-call budget exceeded")
            self.assertEqual(tools.write_operations, 0)

    def test_large_tool_history_is_compacted_without_losing_trace(self) -> None:
        class VerboseModel:
            def __init__(self) -> None:
                self.turn = 0
                self.context_sizes: list[int] = []

            def complete(self, messages, _tools):
                self.turn += 1
                self.context_sizes.append(_context_size(messages))
                if self.turn == 1:
                    calls = (
                        {
                            "id": "write",
                            "type": "function",
                            "function": {
                                "name": "write_file",
                                "arguments": json.dumps(
                                    {
                                        "path": "frontend/src/large.js",
                                        "content": "x" * 9_000,
                                    }
                                ),
                            },
                        },
                    )
                    return SimpleNamespace(
                        tool_calls=calls,
                        raw_message={"role": "assistant", "tool_calls": calls},
                        content="",
                    )
                if self.turn == 2:
                    calls = (
                        {
                            "id": "validate",
                            "type": "function",
                            "function": {
                                "name": "run_validation",
                                "arguments": '{"scope":"quick"}',
                            },
                        },
                    )
                    return SimpleNamespace(
                        tool_calls=calls,
                        raw_message={"role": "assistant", "tool_calls": calls},
                        content="",
                    )
                return SimpleNamespace(
                    tool_calls=(),
                    raw_message={"role": "assistant", "content": "AUDIT PASS"},
                    content="AUDIT PASS",
                )

        def _context_size(messages) -> int:
            return len(json.dumps(messages, ensure_ascii=False))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "frontend").mkdir()
            (root / "backend").mkdir()
            (root / "frontend" / "package.json").write_text(
                json.dumps(
                    {
                        "name": "frontend",
                        "private": True,
                        "scripts": {"build": DUMMY_BUILD},
                    }
                )
            )
            (root / "backend" / "package.json").write_text(
                json.dumps(
                    {
                        "name": "backend",
                        "private": True,
                        "scripts": {"start": 'node -e ""'},
                    }
                )
            )
            trace = ProductionTrace(root / ".arc" / "trace.jsonl")
            model = VerboseModel()
            with patch.dict(os.environ, {"FACTORY26_AGENT_CONTEXT_CHARS": "8000"}):
                result = CodingAgent(
                    model, WorkspaceTools(root, trace, 3923), trace, max_turns=4
                ).implement(
                    [
                        RequirementNode(
                            req_id="R-COMPACT",
                            name="Compact context",
                            description="Create a large source file.",
                            dependencies=(),
                            scenarios=(),
                            visual_reference=(),
                            raw={},
                        )
                    ]
                )
            self.assertTrue(result.completed)
            rows = [
                json.loads(line)
                for line in trace.path.read_text(encoding="utf-8").splitlines()
            ]
            compacted = [
                row for row in rows if row["event"] == "agent_context_compacted"
            ]
            self.assertTrue(compacted)
            self.assertLess(compacted[0]["payload"]["after_characters"], 8_000)
            checkpoint = compacted[0]["payload"]["checkpoint"]
            self.assertEqual(checkpoint["browser_probe_calls"], 0)
            self.assertEqual(checkpoint["browser_probe_verified_revision"], -1)
            self.assertFalse(checkpoint["browser_probe_requires_recheck"])
            self.assertTrue((root / "frontend" / "src" / "large.js").is_file())

    def test_context_compaction_includes_the_current_source_snapshot(
        self,
    ) -> None:
        class RetentionModel:
            def __init__(self) -> None:
                self.turn = 0
                self.saw_current_source = False

            def complete(self, messages, _tools):
                self.turn += 1
                self.saw_current_source = self.saw_current_source or any(
                    message.get("role") == "user"
                    and "<untrusted_current_sources>" in message.get("content", "")
                    and "frontend/src/part-2.js" in message.get("content", "")
                    for message in messages
                )
                if self.turn <= 2:
                    path = f"frontend/src/part-{self.turn}.js"
                    calls = (
                        {
                            "id": f"write-{self.turn}",
                            "type": "function",
                            "function": {
                                "name": "write_file",
                                "arguments": json.dumps(
                                    {"path": path, "content": "x" * 5_000}
                                ),
                            },
                        },
                    )
                    return SimpleNamespace(
                        tool_calls=calls,
                        raw_message={"role": "assistant", "tool_calls": calls},
                        content="",
                    )
                if self.turn == 3:
                    calls = (
                        {
                            "id": "validate",
                            "type": "function",
                            "function": {
                                "name": "run_validation",
                                "arguments": '{"scope":"quick"}',
                            },
                        },
                    )
                    return SimpleNamespace(
                        tool_calls=calls,
                        raw_message={"role": "assistant", "tool_calls": calls},
                        content="",
                    )
                return SimpleNamespace(
                    tool_calls=(),
                    raw_message={"role": "assistant", "content": "AUDIT PASS"},
                    content="AUDIT PASS",
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "frontend").mkdir()
            (root / "backend").mkdir()
            (root / "frontend" / "package.json").write_text(
                json.dumps(
                    {
                        "name": "frontend",
                        "private": True,
                        "scripts": {"build": DUMMY_BUILD},
                    }
                )
            )
            (root / "backend" / "package.json").write_text(
                json.dumps(
                    {
                        "name": "backend",
                        "private": True,
                        "scripts": {"start": 'node -e ""'},
                    }
                )
            )
            trace = ProductionTrace(root / ".arc" / "trace.jsonl")
            model = RetentionModel()
            with patch.dict(os.environ, {"FACTORY26_AGENT_CONTEXT_CHARS": "16000"}):
                result = CodingAgent(
                    model, WorkspaceTools(root, trace, 3924), trace, max_turns=4
                ).implement(
                    [
                        RequirementNode(
                            req_id="R-RETAIN",
                            name="Retain recent turn",
                            description="Create two source files.",
                            dependencies=(),
                            scenarios=(),
                            visual_reference=(),
                            raw={},
                        )
                    ]
                )
            self.assertTrue(result.completed)
            self.assertTrue(model.saw_current_source)
            rows = [
                json.loads(line)
                for line in trace.path.read_text(encoding="utf-8").splitlines()
            ]
            compacted = [
                row for row in rows if row["event"] == "agent_context_compacted"
            ]
            self.assertTrue(
                any(
                    any(
                        item.get("path") == "frontend/src/part-2.js"
                        for item in row["payload"].get("source_snapshot") or []
                    )
                    for row in compacted
                )
            )

    def test_turn_budget_never_auto_accepts_an_unfinished_audit(self) -> None:
        class UnfinishedAuditModel:
            def __init__(self) -> None:
                self.turn = 0

            def complete(self, _messages, _tools):
                self.turn += 1
                if self.turn == 1:
                    calls = (
                        {
                            "id": "write",
                            "type": "function",
                            "function": {
                                "name": "write_file",
                                "arguments": json.dumps(
                                    {
                                        "path": "frontend/src/unfinished.js",
                                        "content": "unfinished\n",
                                    }
                                ),
                            },
                        },
                    )
                elif self.turn == 2:
                    calls = (
                        {
                            "id": "validate",
                            "type": "function",
                            "function": {
                                "name": "run_validation",
                                "arguments": '{"scope":"quick"}',
                            },
                        },
                    )
                else:
                    calls = (
                        {
                            "id": "unfinished-read",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": '{"path":"frontend/src/unfinished.js"}',
                            },
                        },
                    )
                return SimpleNamespace(
                    tool_calls=calls,
                    raw_message={"role": "assistant", "tool_calls": calls},
                    content="",
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "frontend").mkdir()
            (root / "backend").mkdir()
            (root / "frontend" / "package.json").write_text(
                json.dumps(
                    {
                        "name": "frontend",
                        "private": True,
                        "scripts": {"build": DUMMY_BUILD},
                    }
                )
            )
            (root / "backend" / "package.json").write_text(
                json.dumps(
                    {
                        "name": "backend",
                        "private": True,
                        "scripts": {"start": 'node -e ""'},
                    }
                )
            )
            trace = ProductionTrace(root / ".arc" / "trace.jsonl")
            result = CodingAgent(
                UnfinishedAuditModel(),
                WorkspaceTools(root, trace, 3925),
                trace,
                max_turns=3,
            ).implement(
                [
                    RequirementNode(
                        req_id="R-UNFINISHED-AUDIT",
                        name="Reject unfinished audit",
                        description="Create one implementation file.",
                        dependencies=(),
                        scenarios=(),
                        visual_reference=(),
                        raw={},
                    )
                ]
            )
            self.assertFalse(result.completed)
            self.assertEqual(result.summary, "maximum tool turns reached")
            rows = [
                json.loads(line)
                for line in trace.path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(rows[-1]["event"], "agent_session_exhausted")

    def test_oversized_model_request_fails_before_network_io(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = ProductionTrace(root / "trace.jsonl")
            environment = {
                "OPENAI_API_KEY": "test-secret",
                "OPENAI_BASE_URL": "http://127.0.0.1:1/v1",
                "MODEL": "mock-model",
                "FACTORY26_MAX_MODEL_REQUEST_BYTES": "1024",
            }
            with patch.dict(os.environ, environment, clear=False):
                client = OpenAIChatClient(trace)
                with self.assertRaisesRegex(RuntimeError, "byte safety limit"):
                    client.complete(
                        [
                            {"role": "system", "content": "safe"},
                            {"role": "user", "content": "x" * 3_000},
                        ],
                        [],
                    )
            self.assertEqual(client.http_attempt_count, 0)

    def test_invalid_request_policy_fails_before_network_io(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = ProductionTrace(root / "trace.jsonl")
            environment = {
                "OPENAI_API_KEY": "test-secret",
                "OPENAI_BASE_URL": "http://127.0.0.1:1/v1",
                "MODEL": "mock-model",
            }
            with patch.dict(os.environ, environment, clear=False):
                client = OpenAIChatClient(trace)
                with self.assertRaisesRegex(ValueError, "max_attempts"):
                    client.complete([], [], max_attempts=0)
                with self.assertRaisesRegex(ValueError, "timeout"):
                    client.complete([], [], timeout_seconds=241)
            self.assertEqual(client.http_attempt_count, 0)


if __name__ == "__main__":
    unittest.main()
