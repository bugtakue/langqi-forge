from __future__ import annotations

import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tests.protocol_gateway_two_batch import Handler, _last_tool_from_checkpoint


class TwoBatchGatewayTests(unittest.TestCase):
    def test_fixture_resumes_from_agent_context_checkpoint(self) -> None:
        state = {"latest_tool_results": [
            {"tool": "write_file", "ok": True},
            {"tool": "replace_text", "ok": True},
        ]}
        messages = [
            {"role": "system", "content": "fixture"},
            {"role": "user", "content": "Implement [REQ-1]"},
            {"role": "user", "content": (
                "Deterministic context checkpoint; prior turns are in trace. "
                "State:\n" + json.dumps(state) + "\n\n<untrusted_current_sources>"
            )},
        ]
        self.assertEqual(_last_tool_from_checkpoint(messages), "replace_text")
        self.assertEqual(_last_tool_from_checkpoint(messages[:2]), "")

    def test_long_prior_source_requires_real_continuation_before_second_edit(self) -> None:
        Handler.require_source_page_second = True
        Handler.source_tail_seen = False
        Handler.require_full_spec_first = False
        Handler.fail_second = False
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        prompt = (
            'Whole-task index <untrusted_task_outline>{"requirements":[{"id":"REQ-1"},'
            '{"id":"REQ-2"}]}</untrusted_task_outline> Implement [REQ-2]; '
            "prior path: frontend/src/first-feature.js "
            "<untrusted_prior_batch_handoffs>REQ-1: AUDIT PASS: two-batch fixture only"
            "</untrusted_prior_batch_handoffs>"
        )

        def complete(tool: str, result: dict) -> dict:
            messages = [
                {"role": "system", "content": "fixture"},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "", "tool_calls": [{
                    "id": "prior", "type": "function",
                    "function": {"name": tool, "arguments": "{}"},
                }]},
                {"role": "tool", "tool_call_id": "prior", "content": json.dumps(result)},
            ]
            request = Request(
                f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                data=json.dumps({"messages": messages}).encode("utf-8"),
                headers={"content-type": "application/json"},
            )
            with urlopen(request, timeout=2) as response:
                return json.load(response)

        try:
            with self.assertRaises(HTTPError) as missing:
                complete("read_files", {"files": [{
                    "path": "frontend/src/first-feature.js",
                    "content_truncated": False,
                }]})
            self.assertEqual(missing.exception.code, 422)
            page = complete("read_files", {"files": [{
                "path": "frontend/src/first-feature.js",
                "content_truncated": True,
                "next_start_line": 198,
            }]})
            first_call = page["choices"][0]["message"]["tool_calls"][0]
            self.assertEqual(first_call["function"]["name"], "read_file")
            self.assertEqual(
                json.loads(first_call["function"]["arguments"])["start_line"], 198
            )
            more = complete("read_file", {
                "path": "frontend/src/first-feature.js",
                "content": "// prefix only",
                "next_start_line": 401,
            })
            self.assertEqual(
                json.loads(more["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"])["start_line"],
                401,
            )
            edited = complete("read_file", {
                "path": "frontend/src/first-feature.js",
                "content": "// SOURCE_TAIL_VISIBLE_TO_NEXT_BATCH",
                "next_start_line": None,
            })
            self.assertEqual(
                [call["function"]["name"] for call in edited["choices"][0]["message"]["tool_calls"]],
                ["write_file", "replace_text"],
            )
        finally:
            Handler.require_source_page_second = False
            Handler.source_tail_seen = False
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

    def test_second_batch_requires_handoff_and_can_read_prior_module(self) -> None:
        Handler.fail_second = False
        Handler.require_full_spec_first = False
        Handler.requests = 0
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def complete(prompt: str, assistant_tools: list[dict] | None = None) -> dict:
            messages = [
                {"role": "system", "content": "fixture"},
                {"role": "user", "content": prompt},
            ]
            if assistant_tools:
                messages.append(
                    {"role": "assistant", "content": "", "tool_calls": assistant_tools}
                )
            request = Request(
                f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                data=json.dumps({"messages": messages}).encode("utf-8"),
                headers={"content-type": "application/json"},
            )
            with urlopen(request, timeout=2) as response:
                return json.load(response)

        try:
            with self.assertRaises(HTTPError) as error:
                complete("Implement [REQ-2] without prior context")
            self.assertEqual(error.exception.code, 422)
            handoff_prompt = (
                'Whole-task index <untrusted_task_outline>{"requirements":[{"id":"REQ-1"},'
                '{"id":"REQ-2"}]}</untrusted_task_outline> '
                "Implement [REQ-2]; prior path: frontend/src/first-feature.js "
                "<untrusted_prior_batch_handoffs>REQ-1: AUDIT PASS: two-batch fixture only"
                "</untrusted_prior_batch_handoffs>"
            )
            first = complete(handoff_prompt)
            read_call = first["choices"][0]["message"]["tool_calls"][0]
            self.assertEqual(read_call["function"]["name"], "read_files")
            self.assertIn(
                "frontend/src/first-feature.js",
                json.loads(read_call["function"]["arguments"])["paths"],
            )
            second = complete(handoff_prompt, [read_call])
            names = [
                call["function"]["name"]
                for call in second["choices"][0]["message"]["tool_calls"]
            ]
            self.assertEqual(names, ["write_file", "replace_text"])

            Handler.fail_second = True
            blocked = complete(handoff_prompt)
            self.assertIn("AUDIT BLOCKED", blocked["choices"][0]["message"]["content"])
            self.assertEqual(blocked["choices"][0]["message"]["tool_calls"], [])
        finally:
            Handler.fail_second = False
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

    def test_long_spec_protocol_rejects_missing_reader_and_premature_edit(self) -> None:
        Handler.require_full_spec_first = True
        Handler.full_spec_verified = False
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        prompt = (
            'Whole-task index <untrusted_task_outline>{"requirements":'
            '[{"id":"REQ-1"},{"id":"REQ-2"}]}</untrusted_task_outline> '
            "Implement [REQ-1]"
        )

        def complete(
            expose_reader: bool, prior_tool: str = "", tool_result: dict | None = None
        ) -> dict:
            messages = [
                {"role": "system", "content": "fixture"},
                {"role": "user", "content": prompt},
            ]
            if prior_tool:
                messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": prior_tool}}],
                })
            if tool_result is not None:
                messages.append({"role": "tool", "content": json.dumps(tool_result)})
            payload = {"messages": messages}
            if expose_reader:
                payload["tools"] = [
                    {"function": {"name": "read_requirement_spec"}}
                ]
            request = Request(
                f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"content-type": "application/json"},
            )
            with urlopen(request, timeout=2) as response:
                return json.load(response)

        try:
            with self.assertRaises(HTTPError) as missing:
                complete(False)
            self.assertEqual(missing.exception.code, 422)
            first = complete(True)
            call = first["choices"][0]["message"]["tool_calls"][0]
            self.assertEqual(call["function"]["name"], "read_requirement_spec")
            self.assertEqual(
                json.loads(call["function"]["arguments"])["start_char"], 0
            )
            with self.assertRaises(HTTPError) as premature:
                complete(True, "read_files")
            self.assertEqual(premature.exception.code, 422)
            self.assertFalse(Handler.full_spec_verified)
            Handler.full_spec_verified = True
            after_complete = complete(True, "read_files")
            names = [
                call["function"]["name"]
                for call in after_complete["choices"][0]["message"]["tool_calls"]
            ]
            self.assertEqual(names, ["write_file", "replace_text"])
            Handler.review_full_spec_first = True
            Handler.full_spec_revisited = False
            with self.assertRaises(HTTPError) as missing_review:
                complete(True, "read_files")
            self.assertEqual(missing_review.exception.code, 422)
            reviewed = complete(True, "read_requirement_spec", {
                "ok": True,
                "requirement_id": "REQ-1",
                "start_char": 0,
                "review": True,
                "complete": False,
            })
            self.assertEqual(
                reviewed["choices"][0]["message"]["tool_calls"][0]["function"]["name"],
                "read_files",
            )
            self.assertTrue(Handler.full_spec_revisited)
        finally:
            Handler.require_full_spec_first = False
            Handler.full_spec_verified = False
            Handler.review_full_spec_first = False
            Handler.full_spec_revisited = False
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
