import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from factory26_harness.agent import CodingAgent, SYSTEM_PROMPT, _compact_tool_result
from factory26_harness.requirements import flatten_atomic
from factory26_harness.trace import ProductionTrace
from factory26_harness.workspace_tools import MAX_TOOL_RESULT_CHARS, WorkspaceTools


class SourceRangeContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "frontend/app.js"
        self.path.parent.mkdir()
        self.tools = WorkspaceTools(self.root, ProductionTrace(self.root / ".arc/trace.jsonl"), 33219)

    def read(self, **arguments):
        encoded = self.tools.execute("read_file", {"path": "frontend/app.js", **arguments})
        self.assertLessEqual(len(encoded), MAX_TOOL_RESULT_CHARS)
        result = json.loads(encoded)
        self.assertTrue(result["ok"])
        return result

    def test_complete_requested_middle_range_does_not_claim_whole_file(self):
        self.path.write_text("".join(f"const value{i} = {i};\n" for i in range(1, 475)))
        result = self.read(start_line=200, end_line=300)
        self.assertEqual(result["last_line"], 300)
        self.assertEqual(result["requested_end_line"], 300)
        self.assertTrue(result["requested_range_complete"])
        self.assertTrue(result["content_truncated"])
        self.assertEqual(result["next_start_line"], 301)
        self.assertEqual(len(result["content"].splitlines()), 101)
        compact = _compact_tool_result("read_file", result)
        self.assertTrue(compact["requested_range_complete"])
        self.assertTrue(compact["content_truncated"])

    def test_byte_and_line_caps_cannot_claim_requested_range_complete(self):
        self.path.write_text("".join(f"// {i} " + "q" * 100 + "\n" for i in range(900)))
        result = self.read(start_line=1, end_line=300)
        self.assertLess(result["last_line"], 300)
        self.assertFalse(result["requested_range_complete"])
        self.path.write_text("x\n" * 900)
        result = self.read(start_line=1, end_line=700)
        self.assertEqual(result["last_line"], 400)
        self.assertEqual(result["requested_end_line"], 700)
        self.assertFalse(result["requested_range_complete"])

    def test_default_page_eof_and_empty_ranges_are_explicit(self):
        self.path.write_text("x\n" * 900)
        result = self.read()
        self.assertEqual(result["last_line"], 400)
        self.assertTrue(result["requested_range_complete"])
        self.assertTrue(result["content_truncated"])
        result = self.read(start_line=850, end_line=1000)
        self.assertEqual(result["last_line"], 900)
        self.assertTrue(result["requested_range_complete"])
        self.assertFalse(result["content_truncated"])
        self.path.write_text("")
        result = self.read(start_line=20, end_line=40)
        self.assertEqual(result["content"], "")
        self.assertIsNone(result["last_line"])
        self.assertTrue(result["requested_range_complete"])

    def test_oversized_single_line_character_pages_remain_incomplete_until_eof(self):
        source = "文本" * 12000
        self.path.write_text(source)
        result = self.read(start_line=1, end_line=1)
        self.assertTrue(result["character_page_required"])
        self.assertFalse(result["requested_range_complete"])
        cursor, chunks = result["next_start_char"], []
        while cursor is not None:
            result = self.read(start_char=cursor)
            chunks.append(result["content"])
            cursor = result["next_start_char"]
            self.assertEqual(result["requested_range_complete"], cursor is None)
        self.assertEqual("".join(chunks), source)

    def test_batch_cut_and_hash_only_fallback_cannot_claim_complete_ranges(self):
        self.path.write_text("abc\n" * 100)
        with patch("factory26_harness.workspace_tools.MAX_BATCH_RESULT_CONTENT_CHARS", 25):
            result = json.loads(self.tools.execute("read_files", {"paths": ["frontend/app.js"]}))
        row = result["files"][0]
        self.assertTrue(row["content_truncated"])
        self.assertFalse(row["requested_range_complete"])
        compact = _compact_tool_result("read_files", result)
        self.assertFalse(compact["unread_sources"][0]["requested_range_complete"])
        oversized = {"ok": True, "files": [{"path": "frontend/app.js", "content": "x" * 20000,
                        "requested_range_complete": True, "sha256": "a" * 64}]}
        with patch.object(self.tools, "_tool_read_files", return_value=oversized):
            result = json.loads(self.tools.execute("read_files", {"paths": ["frontend/app.js"]}))
        self.assertTrue(result["re_read_files_individually"])
        self.assertFalse(result["files"][0]["requested_range_complete"])
        self.assertNotIn("content", result["files"][0])

    def test_prompt_and_schema_do_not_require_automatic_eof_traversal(self):
        schema = next(s["function"] for s in self.tools.schemas() if s["function"]["name"] == "read_file")
        self.assertIn("requested_range_complete", schema["description"])
        self.assertIn("not automatically to EOF", schema["description"])
        self.assertIn("Read relevant source ranges, not every file to EOF", SYSTEM_PROMPT)
        self.assertIn("Revisit omitted details before relying on them or reporting AUDIT PASS", SYSTEM_PROMPT)

    def test_model_receives_range_contract_after_context_compaction(self):
        self.path.write_text("".join(f"const item{i} = {i};\n" for i in range(1, 475)))
        received = []

        class RangeReader:
            turn = 0

            def complete(self, messages, _schemas):
                self.turn += 1
                if self.turn == 2:
                    received.extend(messages)
                    raise RuntimeError("captured range contract")
                calls = [{"id": "range", "type": "function", "function": {
                    "name": "read_file", "arguments": json.dumps({
                        "path": "frontend/app.js", "start_line": 200, "end_line": 300,
                    })}}]
                return SimpleNamespace(tool_calls=calls, content="inspection " * 10000,
                    raw_message={"role": "assistant", "content": "inspection " * 10000,
                                 "tool_calls": calls})

        nodes = flatten_atomic({"id": "R", "type": "ATOMIC", "name": "Example",
                                "description": "Implement one required action."})
        with patch.dict(os.environ, {"FACTORY26_AGENT_CONTEXT_CHARS": "16000"}):
            with self.assertRaisesRegex(RuntimeError, "captured range contract"):
                CodingAgent(RangeReader(), self.tools, self.tools.trace).implement(nodes)
        observation = json.loads(next(m["content"] for m in received if m["role"] == "tool"))
        self.assertTrue(observation["requested_range_complete"])
        self.assertTrue(observation["content_truncated"])
        self.assertEqual(observation["last_line"], 300)
        checkpoint = next(m["content"] for m in received if "Deterministic context checkpoint" in str(m.get("content")))
        self.assertIn('"requested_range_complete":true', checkpoint)
        self.assertIn("not mandatory work", checkpoint)


if __name__ == "__main__":
    unittest.main()
