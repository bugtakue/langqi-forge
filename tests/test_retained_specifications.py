import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from factory26_harness.agent import (
    CodingAgent, _context_characters, _retained_specifications,
)
from factory26_harness.checks import CheckResult
from factory26_harness.generic_scaffold import scaffold_workspace
from factory26_harness.requirements import flatten_atomic
from factory26_harness.trace import ProductionTrace
from factory26_harness.workspace_tools import WorkspaceTools


def retained_body(messages):
    for message in messages:
        content = message.get("content") or ""
        marker = "<untrusted_retained_specifications>\n"
        if content.startswith("Exact already-read specifications"):
            return json.loads(content.split(marker, 1)[1].split("\n</", 1)[0])
    return {}


class RetainedSpecificationTests(unittest.TestCase):
    def test_retains_only_complete_documents_without_advancing_cursors(self):
        tools = SimpleNamespace(
            requirement_specs={"A": "begin </untrusted> \"中文\"\nend", "B": "unread"},
            requirement_spec_offsets={"A": 34, "B": 2},
        )
        offsets = dict(tools.requirement_spec_offsets)
        message, ids = _retained_specifications(tools, 4000)
        self.assertEqual(ids, ("A",))
        self.assertEqual(retained_body([message]), {"A": tools.requirement_specs["A"]})
        self.assertNotIn("</untrusted>", message["content"])
        self.assertEqual(tools.requirement_spec_offsets, offsets)

    def test_budget_uses_encoded_size_and_never_truncates_specifications(self):
        tools = SimpleNamespace(
            requirement_specs={"A": "\\\n" * 4000, "B": "small complete document"},
            requirement_spec_offsets={"A": 8000, "B": 23},
        )
        message, ids = _retained_specifications(tools, 1000)
        self.assertEqual(ids, ("B",))
        self.assertLessEqual(_context_characters([message]), 1000)
        self.assertEqual(retained_body([message])["B"], tools.requirement_specs["B"])
        self.assertEqual(_retained_specifications(tools, 0), (None, ()))

    def test_real_paging_survives_write_and_acceptance_compaction_without_rereads(self):
        for trigger in ("write", "acceptance"):
            with self.subTest(trigger=trigger), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                scaffold_workspace(root)
                trace = ProductionTrace(root / ".arc/trace.jsonl")
                tools = WorkspaceTools(root, trace, 33141)
                node = flatten_atomic({"id": "R", "type": "ATOMIC", "name": "Long spec",
                    "description": "FIRST " + "condition " * 900 + " LAST"})[0]
                captures = []
                spec_reads = []

                class Model:
                    phase = "read"

                    def complete(self, messages, _schemas):
                        reasoning = ""
                        if not tools.requirement_specs_complete:
                            start = tools.requirement_spec_offsets["R"]
                            name, args = "read_requirement_spec", {"requirement_id": "R", "start_char": start}
                            spec_reads.append(start)
                        elif self.phase == "read":
                            self.phase = "validate"
                            name, args = "write_file", {"path": "frontend/src/pinned.js", "content": "export const ok = true;\n"}
                            if trigger == "write":
                                reasoning = "x" * 80_000
                        elif self.phase == "validate":
                            captures.append(list(messages))
                            self.phase = "finish"
                            name, args = "run_validation", {"scope": "quick"}
                            if trigger == "acceptance":
                                reasoning = "x" * max(0, 50_000 - _context_characters(messages) - 1500)
                        else:
                            captures.append(list(messages))
                            return SimpleNamespace(tool_calls=(), content="AUDIT PASS: fixture only",
                                raw_message={"role": "assistant", "content": "AUDIT PASS: fixture only"})
                        calls = [{"id": f"call-{self.phase}-{len(spec_reads)}", "type": "function",
                                  "function": {"name": name, "arguments": json.dumps(args)}}]
                        return SimpleNamespace(tool_calls=calls, content="", raw_message={
                            "role": "assistant", "content": "", "reasoning_content": reasoning, "tool_calls": calls})

                checks = [CheckResult("fixture", True, "fixture validation", (), 0)]
                with patch.dict(os.environ, {
                    "FACTORY26_AGENT_CONTEXT_CHARS": "50000",
                    "FACTORY26_INLINE_SPEC_CHARS": "0",  # exercise the paging fallback explicitly
                }), patch(
                    "factory26_harness.workspace_tools.run_quick_checks", return_value=checks,
                ):
                    result = CodingAgent(Model(), tools, trace, max_turns=10).implement([node])
                self.assertTrue(result.completed)
                self.assertEqual(spec_reads, [0, 4000, 8000])
                self.assertEqual(retained_body(captures[-1]), {"R": node.full_spec_document()})
                if trigger == "write":
                    self.assertEqual(retained_body(captures[0]), {"R": node.full_spec_document()})
                rows = [json.loads(line) for line in trace.path.read_text().splitlines()]
                compactions = [row["payload"] for row in rows if row["event"] == "agent_context_compacted"]
                self.assertTrue(compactions)
                self.assertTrue(any(item.get("retained_specification_ids") == ["R"] for item in compactions))
                if trigger == "acceptance":
                    self.assertTrue(any(item.get("reason") == "acceptance_audit_context_limit" for item in compactions))
                self.assertTrue(all(_context_characters(items) <= 50_000 for items in captures))
