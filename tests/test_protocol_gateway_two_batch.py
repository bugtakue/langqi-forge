from __future__ import annotations

import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tests.protocol_gateway_two_batch import Handler


class TwoBatchGatewayTests(unittest.TestCase):
    def test_second_batch_requires_handoff_and_can_read_prior_module(self) -> None:
        Handler.fail_second = False
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


if __name__ == "__main__":
    unittest.main()
