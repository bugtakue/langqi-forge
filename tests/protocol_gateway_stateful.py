"""Fixed-response state-isolation fixture, never a real-model score."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


SERVER_IMPORT = 'import { readFile } from "node:fs/promises";'
SERVER_IMPORT_WITH_STORAGE = (
    SERVER_IMPORT + '\nimport { loadState, updateState } from "./storage.mjs";'
)
HEALTH_ROUTE = '    if (url.pathname === "/api/health") {'
COUNTER_ROUTES = '''    if (url.pathname === "/api/state" && request.method === "GET") {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(await loadState()));
      return;
    }
    if (url.pathname === "/api/increment" && request.method === "POST") {
      const next = await updateState((state) => ({ ...state, count: state.count + 1 }));
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(next));
      return;
    }
''' + HEALTH_ROUTE
APP = '''document.querySelector("#app").innerHTML =
  '<h1>Example</h1><button type="button">Increment</button><p id="status">Count: 0</p>';
document.querySelector("button").addEventListener("click", async () => {
  const response = await fetch("/api/increment", { method: "POST" });
  const state = await response.json();
  document.querySelector("#status").textContent = `Count: ${state.count}`;
});'''


class Handler(BaseHTTPRequestHandler):
    requests = 0

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        size = int(self.headers.get("content-length") or 0)
        payload = json.loads(self.rfile.read(size))
        previous_tools = [
            call.get("function", {}).get("name")
            for message in payload.get("messages", [])
            if isinstance(message, dict) and message.get("role") == "assistant"
            for call in message.get("tool_calls") or []
            if isinstance(call, dict)
        ]
        last_tool = previous_tools[-1] if previous_tools else ""
        if not last_tool:
            instructions = [
                (
                    "read_files",
                    {"paths": [
                        "frontend/src/app.js",
                        "frontend/src/index.html",
                        "frontend/src/styles.css",
                        "backend/server.mjs",
                        "backend/data/state.json",
                    ]},
                )
            ]
        elif last_tool == "read_files":
            instructions = [
                (
                    "replace_text",
                    {"path": "backend/server.mjs", "old": SERVER_IMPORT, "new": SERVER_IMPORT_WITH_STORAGE},
                ),
                (
                    "replace_text",
                    {"path": "backend/server.mjs", "old": HEALTH_ROUTE, "new": COUNTER_ROUTES},
                ),
                (
                    "replace_text",
                    {"path": "backend/data/state.json", "old": "{}\n", "new": '{"count":0}\n'},
                ),
                (
                    "replace_text",
                    {
                        "path": "frontend/src/app.js",
                        "old": "// The coding agent implements the requested application here.",
                        "new": APP,
                    },
                ),
            ]
        elif last_tool == "replace_text":
            instructions = [("run_validation", {"scope": "quick"})]
        elif last_tool == "run_validation":
            instructions = [
                (
                    "browser_probe",
                    {"steps": [{
                        "action": "click",
                        "role": "button",
                        "name": "Increment",
                        "expect_text": ["Count: 1"],
                    }]},
                )
            ]
        else:
            instructions = []

        type(self).requests += 1
        tool_calls = [
            {
                "id": f"stateful-fixture-{type(self).requests}-{index}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
            for index, (name, arguments) in enumerate(instructions, 1)
        ]
        body = {
            "id": f"stateful-fixture-{type(self).requests}",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "AUDIT PASS: isolated stateful protocol fixture" if not tool_calls else "",
                    "tool_calls": tool_calls,
                },
                "finish_reason": "tool_calls" if tool_calls else "stop",
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=19793)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"stateful protocol fixture listening on {args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
