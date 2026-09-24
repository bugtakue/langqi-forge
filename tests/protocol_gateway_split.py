"""Fixed-response split-retry protocol fixture, never a coding-model benchmark."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


APP = '''const app = document.querySelector("#app");
app.innerHTML = '<h1>Salvaged</h1><button type="button" id="try">Try</button><p id="status"></p>';
document.querySelector("#try").addEventListener("click", () => {
  document.querySelector("#status").textContent = "Clicked";
});
'''
STARTER_PATHS = [
    "frontend/src/app.js",
    "frontend/src/index.html",
    "frontend/src/styles.css",
    "backend/server.mjs",
    "backend/data/state.json",
]


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
        messages = payload.get("messages") or []
        prompt = str(messages[1].get("content") or "") if len(messages) > 1 else ""
        ids = [f"REQ-{index}" for index in range(1, 5) if f"[REQ-{index}]" in prompt]
        if not ids:
            self.send_error(422, "unknown fixture requirement batch")
            return
        # Fail the original four-node attempt and the latter half. The first
        # half is allowed to build a real local interaction after the split.
        calls = []
        if ids == ["REQ-1", "REQ-2"]:
            previous_tools = [
                call.get("function", {}).get("name")
                for message in messages
                if isinstance(message, dict) and message.get("role") == "assistant"
                for call in message.get("tool_calls") or []
                if isinstance(call, dict)
            ]
            last_tool = previous_tools[-1] if previous_tools else ""
            if not last_tool:
                calls = [("read_files", {"paths": STARTER_PATHS})]
            elif last_tool == "read_files":
                calls = [("replace_text", {
                    "path": "frontend/src/app.js",
                    "old": "// The coding agent implements the requested application here.",
                    "new": APP.rstrip("\n"),
                })]
            elif last_tool == "replace_text":
                calls = [("run_validation", {"scope": "quick"})]
            elif last_tool == "run_validation":
                calls = [("browser_probe", {"steps": [{
                    "action": "click", "role": "button", "name": "Try",
                    "expect_text": ["Clicked"],
                }]})]
        type(self).requests += 1
        turn = type(self).requests
        tool_calls = [
            {
                "id": f"split-fixture-{turn}-{index}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
            for index, (name, arguments) in enumerate(calls)
        ]
        body = {
            "id": f"split-fixture-{turn}",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "" if tool_calls else (
                        "AUDIT PASS: fixture first half validated"
                        if ids == ["REQ-1", "REQ-2"]
                        else "AUDIT BLOCKED: intentional protocol failure"
                    ),
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
    parser.add_argument("--port", type=int, default=19787)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"split protocol fixture listening on {args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
