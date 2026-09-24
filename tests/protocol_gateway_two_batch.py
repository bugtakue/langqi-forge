"""Two-batch protocol fixture; this is not a real coding model or score evidence."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


FIRST_APP = '''import { message } from "./first-feature.js";
const app = document.querySelector("#app");
app.innerHTML = `<h1>${message}</h1><button type="button" id="try">Try</button><p id="status"></p>`;
document.querySelector("#try").addEventListener("click", () => {
  document.querySelector("#status").textContent = "Clicked";
});
'''
SECOND_APP = 'import { attachSecond } from "./second-feature.js";\n' + FIRST_APP + 'attachSecond();\n'
SECOND_MODULE = '''export function attachSecond() {
  const second = document.createElement("button");
  second.type = "button";
  second.textContent = "Second";
  second.addEventListener("click", () => {
    document.querySelector("#status").textContent = "Ready";
  });
  document.querySelector("#app").append(second);
}
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
    fail_second = False
    truncate_first = False
    truncated_once = False
    recovery_verified = False

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        size = int(self.headers.get("content-length") or 0)
        payload = json.loads(self.rfile.read(size))
        messages = payload.get("messages") or []
        if len(messages) < 2 or not isinstance(messages[1], dict):
            self.send_error(422, "missing implementation prompt")
            return
        prompt = str(messages[1].get("content") or "")
        second_batch = "[REQ-2]" in prompt
        if not second_batch and "[REQ-1]" not in prompt:
            self.send_error(422, "unknown requirement batch")
            return
        if (
            "<untrusted_task_outline>" not in prompt
            or '"id":"REQ-2"' not in prompt
        ):
            self.send_error(422, "whole-task architecture index was not supplied")
            return
        if second_batch and "frontend/src/first-feature.js" not in prompt:
            self.send_error(422, "prior batch source path was not handed off")
            return
        if type(self).truncate_first and not second_batch and not type(self).truncated_once:
            type(self).truncated_once = True
            type(self).requests += 1
            body = {
                "id": "fixture-length-truncated-tool-call",
                "choices": [{
                    "finish_reason": "length",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{
                            "id": "truncated-unsafe-write",
                            "type": "function",
                            "function": {
                                "name": "write_file",
                                "arguments": json.dumps({
                                    "path": "frontend/src/TRUNCATED_UNSAFE.js",
                                    "content": "This output must never be executed.",
                                }),
                            },
                        }],
                    },
                }],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            }
            encoded = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        if type(self).truncate_first and not second_batch and not type(self).recovery_verified:
            if not any(
                message.get("role") == "user"
                and "None of its tool calls were executed" in str(message.get("content") or "")
                for message in messages
            ) or any(
                message.get("role") == "assistant" and message.get("tool_calls")
                for message in messages
            ):
                self.send_error(422, "truncated tool call was not discarded safely")
                return
            type(self).recovery_verified = True
        previous_tools = [
            call.get("function", {}).get("name")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "assistant"
            for call in message.get("tool_calls") or []
            if isinstance(call, dict)
        ]
        last_tool = previous_tools[-1] if previous_tools else ""
        if second_batch and type(self).fail_second:
            name_and_arguments = []
        elif not last_tool:
            name_and_arguments = [
                (
                    "read_files",
                    {"paths": STARTER_PATHS + (["frontend/src/first-feature.js"] if second_batch else [])},
                )
            ]
        elif last_tool == "read_files":
            if second_batch:
                name_and_arguments = [
                    ("write_file", {"path": "frontend/src/second-feature.js", "content": SECOND_MODULE}),
                    ("replace_text", {"path": "frontend/src/app.js", "old": FIRST_APP, "new": SECOND_APP}),
                ]
            else:
                name_and_arguments = [
                    (
                        "write_file",
                        {"path": "frontend/src/first-feature.js", "content": 'export const message = "Example";\n'},
                    ),
                    (
                        "replace_text",
                        {
                            "path": "frontend/src/app.js",
                            "old": "// The coding agent implements the requested application here.",
                            "new": FIRST_APP.rstrip("\n"),
                        },
                    ),
                ]
        elif last_tool == "replace_text":
            name_and_arguments = [("run_validation", {"scope": "quick"})]
        elif last_tool == "run_validation":
            name_and_arguments = [
                (
                    "browser_probe",
                    {
                        "steps": [
                            {
                                "action": "click",
                                "role": "button",
                                "name": "Second" if second_batch else "Try",
                                "expect_text": ["Ready" if second_batch else "Clicked"],
                            }
                        ]
                    },
                )
            ]
        else:
            name_and_arguments = []
        type(self).requests += 1
        turn = type(self).requests
        tool_calls = [
            {
                "id": f"two-batch-{turn}-{index}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
            for index, (name, arguments) in enumerate(name_and_arguments)
        ]
        body = {
            "id": f"two-batch-fixture-{turn}",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": (
                            ""
                            if tool_calls
                            else "AUDIT BLOCKED: intentional second-batch failure"
                            if second_batch and type(self).fail_second
                            else "AUDIT PASS: two-batch fixture only"
                        ),
                        "tool_calls": tool_calls,
                    },
                    "finish_reason": "tool_calls" if tool_calls else "stop",
                }
            ],
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
    parser.add_argument("--port", type=int, default=19786)
    parser.add_argument("--fail-second", action="store_true")
    parser.add_argument("--truncate-first", action="store_true")
    args = parser.parse_args()
    port = args.port
    Handler.fail_second = args.fail_second
    Handler.truncate_first = args.truncate_first
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"two-batch protocol fixture listening on {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
