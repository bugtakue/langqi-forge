from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from factory26_harness.agent import CodingAgent
from factory26_harness.model import OpenAIChatClient
from factory26_harness.requirements import RequirementNode
from factory26_harness.trace import ProductionTrace
from factory26_harness.workspace_tools import WorkspaceTools


class _ModelHandler(BaseHTTPRequestHandler):
    calls = 0

    def log_message(self, *_args) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("content-length") or 0)
        json.loads(self.rfile.read(length))
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
                            "arguments": json.dumps({"path": "frontend/src/generated.txt", "content": "generated\n"}),
                        },
                    }
                ],
            }
        else:
            message = {"role": "assistant", "content": "Implemented the requested file."}
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
    def test_openai_tool_loop_edits_workspace_and_tracks_usage(self) -> None:
        _ModelHandler.calls = 0
        server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
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
                    result = CodingAgent(client, tools, trace, max_turns=4).implement([node])
                self.assertTrue(result.completed)
                self.assertEqual((root / "frontend" / "src" / "generated.txt").read_text(), "generated\n")
                self.assertEqual(client.total_prompt_tokens, 20)
                self.assertEqual(client.total_completion_tokens, 10)
                self.assertNotIn("test-secret", (root / ".arc" / "trace.jsonl").read_text(encoding="utf-8"))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
