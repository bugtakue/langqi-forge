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
LONG_FIRST_MODULE = (
    'export const message = "Example";\n'
    + "//\n" * 500
    + "// SOURCE_TAIL_VISIBLE_TO_NEXT_BATCH\n"
)


class Handler(BaseHTTPRequestHandler):
    requests = 0
    fail_second = False
    auth_fail_second = False
    truncate_first = False
    truncated_once = False
    recovery_verified = False
    repair_first_audit = False
    audit_repair_verified = False
    require_full_spec_first = False
    full_spec_verified = False
    review_full_spec_first = False
    full_spec_revisited = False
    require_source_page_second = False
    source_tail_seen = False

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
        if second_batch and (
            "<untrusted_prior_batch_handoffs>" not in prompt
            or "REQ-1: AUDIT PASS: two-batch fixture only" not in prompt
        ):
            self.send_error(422, "prior batch contract summary was not handed off")
            return
        if second_batch and type(self).auth_fail_second:
            type(self).requests += 1
            encoded = b"invalid key: fixture-sensitive-value"
            self.send_response(401)
            self.send_header("content-type", "text/plain")
            self.send_header("content-length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
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
        spec_page_action = None
        if type(self).require_full_spec_first and not second_batch:
            available_tools = {
                item.get("function", {}).get("name")
                for item in payload.get("tools") or [] if isinstance(item, dict)
            }
            if "read_requirement_spec" not in available_tools:
                self.send_error(422, "long requirement reader was not exposed")
                return
            if not last_tool:
                spec_page_action = (
                    "read_requirement_spec", {"requirement_id": "REQ-1", "start_char": 0}
                )
            elif last_tool == "read_requirement_spec":
                pages = [
                    json.loads(str(message.get("content") or "{}"))
                    for message in messages if message.get("role") == "tool"
                    and '"requirement_id": "REQ-1"' in str(message.get("content") or "")
                ]
                if not pages:
                    self.send_error(422, "long requirement reader returned no page")
                    return
                last_page = pages[-1]
                if last_page.get("review"):
                    if (
                        not type(self).full_spec_verified
                        or not type(self).review_full_spec_first
                        or last_page.get("start_char") != 0
                    ):
                        self.send_error(422, "unexpected long specification review")
                        return
                    type(self).full_spec_revisited = True
                    last_tool = ""
                elif not last_page.get("complete"):
                    spec_page_action = (
                        "read_requirement_spec", {
                            "requirement_id": "REQ-1",
                            "start_char": last_page["next_start_char"],
                        }
                    )
                else:
                    full_text = "".join(str(page.get("content") or "") for page in pages)
                    if (
                        len(full_text) != last_page.get("total_chars")
                        or "The state after clicking Try must show" not in full_text
                    ):
                        self.send_error(422, "original long specification was not read completely")
                        return
                    type(self).full_spec_verified = True
                    if type(self).review_full_spec_first:
                        spec_page_action = (
                            "read_requirement_spec", {"requirement_id": "REQ-1", "start_char": 0}
                        )
                    else:
                        last_tool = ""
            else:
                if not type(self).full_spec_verified or (
                    type(self).review_full_spec_first
                    and not type(self).full_spec_revisited
                ):
                    self.send_error(422, "attempted implementation before reading full specification")
                    return
        if spec_page_action is not None:
            name_and_arguments = [spec_page_action]
        elif type(self).require_source_page_second and second_batch and last_tool in {"read_files", "read_file"}:
            tool_results = [
                json.loads(str(message.get("content") or "{}"))
                for message in messages
                if isinstance(message, dict) and message.get("role") == "tool"
            ]
            if not tool_results:
                self.send_error(422, "source read returned no tool result")
                return
            latest = tool_results[-1]
            if last_tool == "read_files":
                source = next(
                    (
                        item for item in latest.get("files") or []
                        if item.get("path") == "frontend/src/first-feature.js"
                    ),
                    None,
                )
                if not source or not source.get("content_truncated"):
                    self.send_error(422, "long prior source was not marked as incomplete")
                    return
                cursor = source.get("next_start_line")
                if not isinstance(cursor, int) or cursor <= 1:
                    self.send_error(422, "missing long-source continuation line")
                    return
                name_and_arguments = [(
                    "read_file",
                    {"path": "frontend/src/first-feature.js", "start_line": cursor},
                )]
            elif latest.get("path") != "frontend/src/first-feature.js":
                self.send_error(422, "wrong prior source was read")
                return
            elif "SOURCE_TAIL_VISIBLE_TO_NEXT_BATCH" in str(latest.get("content") or ""):
                type(self).source_tail_seen = True
                last_tool = "read_files"
                name_and_arguments = []
            elif isinstance(latest.get("next_start_line"), int):
                name_and_arguments = [(
                    "read_file",
                    {
                        "path": "frontend/src/first-feature.js",
                        "start_line": latest["next_start_line"],
                    },
                )]
            else:
                self.send_error(422, "prior source tail was not read")
                return
            if type(self).source_tail_seen:
                name_and_arguments = [
                    ("write_file", {"path": "frontend/src/second-feature.js", "content": SECOND_MODULE}),
                    ("replace_text", {"path": "frontend/src/app.js", "old": FIRST_APP, "new": SECOND_APP}),
                ]
        elif second_batch and type(self).fail_second:
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
                        {
                            "path": "frontend/src/first-feature.js",
                            "content": (
                                LONG_FIRST_MODULE if type(self).require_source_page_second
                                else 'export const message = "Example";\n'
                            ),
                        },
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
        elif (
            last_tool == "write_file"
            and type(self).repair_first_audit
            and not second_batch
            and "browser_probe" in previous_tools
        ):
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
        elif last_tool == "browser_probe" and type(self).repair_first_audit and not second_batch:
            if previous_tools.count("browser_probe") == 1:
                name_and_arguments = [
                    ("write_file", {
                        "path": "frontend/src/audit-repair.js",
                        "content": "export const audited = true;\n",
                    })
                ]
            else:
                audits = [
                    str(message.get("content") or "") for message in messages
                    if message.get("role") == "user"
                    and "<untrusted_changed_sources>" in str(message.get("content") or "")
                ]
                if not audits or "frontend/src/audit-repair.js" not in audits[-1]:
                    self.send_error(422, "latest repaired revision was not re-audited")
                    return
                type(self).audit_repair_verified = True
                name_and_arguments = []
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
    parser.add_argument("--auth-fail-second", action="store_true")
    parser.add_argument("--truncate-first", action="store_true")
    parser.add_argument("--repair-first-audit", action="store_true")
    parser.add_argument("--require-full-spec-first", action="store_true")
    parser.add_argument("--review-full-spec-first", action="store_true")
    parser.add_argument("--require-source-page-second", action="store_true")
    args = parser.parse_args()
    if args.review_full_spec_first and not args.require_full_spec_first:
        parser.error("--review-full-spec-first requires --require-full-spec-first")
    port = args.port
    Handler.fail_second = args.fail_second
    Handler.auth_fail_second = args.auth_fail_second
    Handler.truncate_first = args.truncate_first
    Handler.repair_first_audit = args.repair_first_audit
    Handler.require_full_spec_first = args.require_full_spec_first
    Handler.review_full_spec_first = args.review_full_spec_first
    Handler.require_source_page_second = args.require_source_page_second
    Handler.source_tail_seen = False
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"two-batch protocol fixture listening on {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
