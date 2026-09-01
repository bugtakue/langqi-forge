from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.client import RemoteDisconnected
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from factory26_harness.agent import CodingAgent
from factory26_harness.model import OpenAIChatClient
from factory26_harness.requirements import RequirementNode
from factory26_harness.trace import ProductionTrace
from factory26_harness.workspace_tools import WorkspaceTools


class _ModelHandler(BaseHTTPRequestHandler):
    calls = 0
    payloads: list[dict] = []

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
        else:
            message = {
                "role": "assistant",
                "content": "Implemented the requested file.",
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


class ModelLoopTests(unittest.TestCase):
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
            self.assertIn("closed", errors[0]["payload"]["error"])

    def test_openai_tool_loop_edits_workspace_and_tracks_usage(self) -> None:
        _ModelHandler.calls = 0
        _ModelHandler.payloads = []
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
                            "scripts": {"build": 'node -e ""'},
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
                self.assertEqual(client.total_prompt_tokens, 40)
                self.assertEqual(client.total_completion_tokens, 20)
                self.assertEqual(result.turns, 4)
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
                        for message in final_messages
                    )
                )
                self.assertNotIn(
                    "test-secret",
                    (root / ".arc" / "trace.jsonl").read_text(encoding="utf-8"),
                )
        finally:
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
