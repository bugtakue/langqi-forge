"""Local OpenAI-compatible protocol fixture; never use as performance evidence."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    calls = 0
    exercise_browser = False

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        size = int(self.headers.get("content-length") or 0)
        request = json.loads(self.rfile.read(size))
        type(self).calls += 1
        turn = type(self).calls
        previous_tools = [
            call.get("function", {}).get("name")
            for message in request.get("messages", [])
            if isinstance(message, dict) and message.get("role") == "assistant"
            for call in message.get("tool_calls") or []
            if isinstance(call, dict)
        ]
        last_tool = previous_tools[-1] if previous_tools else ""
        if not last_tool:
            name = "read_files"
            arguments = {
                "paths": [
                    "frontend/src/app.js",
                    "frontend/src/index.html",
                    "frontend/src/styles.css",
                    "backend/server.mjs",
                    "backend/data/state.json",
                ]
            }
        elif last_tool == "read_files":
            name = "replace_text"
            arguments = {
                "path": "frontend/src/app.js",
                "old": "// The coding agent implements the requested application here.",
                "new": (
                    'document.querySelector("#app").innerHTML = '
                    '"<h1>Example</h1><button type=\\"button\\">Try</button>'
                    '<p id=\\"status\\"></p>";\n'
                    'document.querySelector("button").addEventListener("click", () => {\n'
                    '  document.querySelector("#status").textContent = "Clicked";\n'
                    '});'
                    if self.exercise_browser
                    else 'document.querySelector("#app").innerHTML = "<h1>Example</h1>";'
                ),
            }
        elif last_tool == "replace_text":
            name = "run_validation"
            arguments = {"scope": "quick"}
        elif last_tool == "run_validation" and self.exercise_browser:
            name = "browser_probe"
            arguments = {
                "steps": [
                    {
                        "action": "click",
                        "role": "button",
                        "name": "Try",
                        "expect_text": ["Clicked"],
                    }
                ]
            }
        else:
            name = ""
            arguments = {}
        tool_calls = (
            [
                {
                    "id": f"fixture-tool-{turn}",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(arguments),
                    },
                }
            ]
            if name
            else []
        )
        body = {
            "id": f"protocol-fixture-{turn}",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "AUDIT PASS: protocol fixture completed" if not name else "",
                        "tool_calls": tool_calls,
                    },
                    "finish_reason": "tool_calls" if name else "stop",
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        encoded = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=19786)
    parser.add_argument("--exercise-browser", action="store_true")
    args = parser.parse_args()
    Handler.exercise_browser = args.exercise_browser
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"protocol fixture listening on {args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
