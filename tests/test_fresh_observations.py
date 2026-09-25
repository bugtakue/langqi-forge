import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from factory26_harness.agent import CodingAgent, _fresh_observation_messages
from factory26_harness.generic_scaffold import scaffold_workspace
from factory26_harness.requirements import flatten_atomic
from factory26_harness.trace import ProductionTrace
from factory26_harness.workspace_tools import WorkspaceTools


class FreshObservationTests(unittest.TestCase):
    def test_parallel_spec_pages_are_delivered_before_compaction_can_forget_them(self):
        nodes = flatten_atomic({"id": "ROOT", "type": "FOLDER", "children": [
            {"id": f"R-{i}", "type": "ATOMIC", "name": f"Feature {i}",
             "description": f"UNIQUE_PAGE_{i} " + "Condition " * 900}
            for i in range(4)
        ]})
        received = []

        class PageReader:
            turn = 0

            def complete(self, messages, _schemas):
                self.turn += 1
                if self.turn == 2:
                    received.extend(json.loads(m["content"]) for m in messages
                                    if m["role"] == "tool")
                    raise RuntimeError("capture finished")
                calls = [{"id": f"read-{i}", "type": "function", "function": {
                    "name": "read_requirement_spec", "arguments": json.dumps({
                        "requirement_id": node.req_id, "start_char": 0,
                    })}} for i, node in enumerate(nodes)]
                return SimpleNamespace(tool_calls=calls, content="", raw_message={
                    "role": "assistant", "tool_calls": calls,
                })

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold_workspace(root)
            trace = ProductionTrace(root / ".arc/trace.jsonl")
            with patch.dict(os.environ, {"FACTORY26_AGENT_CONTEXT_CHARS": "16000"}):
                agent = CodingAgent(PageReader(), WorkspaceTools(root, trace, 33211), trace)
                with self.assertRaisesRegex(RuntimeError, "capture finished"):
                    agent.implement(nodes)
            self.assertEqual(len(received), 4)
            for i, page in enumerate(received):
                self.assertTrue(page["ok"])
                self.assertIn(f"UNIQUE_PAGE_{i}", page["content"])
            rows = [json.loads(line) for line in trace.path.read_text().splitlines()]
            self.assertTrue(any(row["event"] == "agent_context_compacted" for row in rows))

    def test_mixed_write_read_call_pairing_is_preserved_without_write_body(self):
        calls = [{"id": name, "function": {"name": name, "arguments": "{}"}}
                 for name in ("write_file", "read_file")]
        messages = [{"role": "assistant", "content": "", "tool_calls": calls},
                    {"role": "tool", "tool_call_id": "write_file", "content": "written"},
                    {"role": "tool", "tool_call_id": "read_file", "content": "new observation"}]
        retained = _fresh_observation_messages(messages)
        self.assertEqual(len(retained), 2)
        self.assertEqual([c["id"] for c in retained[0]["tool_calls"]], ["read_file"])
        self.assertEqual(retained[1]["content"], "new observation")
