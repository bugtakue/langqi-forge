import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from factory26_harness.agent import (
    AgentRun, CodingAgent, _context_characters, _prefilled_specifications, _retained_specifications,
)
from factory26_harness.checks import CheckResult
from factory26_harness.generic_scaffold import scaffold_workspace
from factory26_harness.requirements import flatten_atomic
from factory26_harness.trace import ProductionTrace
from factory26_harness.workspace_tools import WorkspaceTools


def prefilled_body(text):
    marker = "<untrusted_prefilled_specifications>\n"
    return json.loads(text.split(marker, 1)[1].split("\n</", 1)[0])


class PrefilledSpecificationTests(unittest.TestCase):
    def test_only_whole_documents_fit_after_json_escaping(self):
        original = {"large": "\\\n" * 4000, "small": '完整 </untrusted> "尾部"'}
        text, selected = _prefilled_specifications(original, 900)
        self.assertEqual(selected, {"small": original["small"]})
        self.assertEqual(prefilled_body(text), selected)
        self.assertNotIn("</untrusted>", text)
        self.assertLessEqual(_context_characters([{"role": "user", "content": text}]), 900)
        self.assertEqual(_prefilled_specifications(original, 0), ("", {}))
        self.assertEqual(_prefilled_specifications(original, -1), ("", {}))

    def test_mismatched_or_foreign_receipt_never_advances_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = WorkspaceTools(root, ProductionTrace(root / ".arc/trace.jsonl"), 33241)
            tools.register_requirement_specs({"A": "whole original", "B": "other original"})
            for invalid in [{"A": "partial"}, {"C": "foreign"},
                            {"A": "whole original", "B": "wrong"}]:
                with self.assertRaises(ValueError):
                    tools.register_inline_requirement_delivery(invalid)
                self.assertEqual(tools.requirement_spec_offsets, {"A": 0, "B": 0})
            tools.register_inline_requirement_delivery({"A": "whole original"})
            self.assertFalse(tools.requirement_specs_complete)
            failed = json.loads(tools.execute("write_file", {
                "path": "frontend/app.js", "content": "export {};",
            }))
            self.assertFalse(failed["ok"])
            self.assertIn("B", failed["error"])
            names = [s["function"]["name"] for s in tools.schemas()]
            self.assertNotIn("register_inline_requirement_delivery", names)
            self.assertFalse(json.loads(tools.execute("register_inline_requirement_delivery", {}))["ok"])
            review = json.loads(tools.execute("read_requirement_spec", {"requirement_id": "A", "start_char": 0}))
            self.assertTrue(review["review"])
            self.assertEqual(review["content"], "whole original")
            tools.execute("read_requirement_spec", {"requirement_id": "B", "start_char": 0})
            self.assertTrue(tools.requirement_specs_complete)
            retained, ids = _retained_specifications(tools, 4000, in_initial_prompt=("A",))
            self.assertEqual(ids, ("B",))
            self.assertNotIn("whole original", retained["content"])
            self.assertEqual(tools.requirement_spec_access_state()[0]["initial_delivery"], "initial_prompt")
            # A new session without the old prompt must not omit an old prefill.
            self.assertEqual(_retained_specifications(tools, 4000)[1], ("A", "B"))

    def test_first_request_has_exact_original_and_compaction_never_loses_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold_workspace(root)
            trace = ProductionTrace(root / ".arc/trace.jsonl")
            tools = WorkspaceTools(root, trace, 33242)
            node = flatten_atomic({
                "id": "R", "type": "ATOMIC", "name": "Assigned fixture",
                "description": "begin " + "condition " * 900 + " END",
                "unknown_acceptance": {"actor": "reader", "constraint": "original extra field"},
            })[0]
            requests = []

            class Model:
                phase = 0

                def complete(self, messages, _schemas):
                    self.phase += 1
                    requests.append(list(messages))
                    if self.phase == 1:
                        name, args = "write_file", {"path": "frontend/src/prefill.js", "content": "export const ok = true;"}
                    elif self.phase == 2:
                        name, args = "run_validation", {"scope": "quick"}
                    else:
                        return SimpleNamespace(tool_calls=(), content="AUDIT PASS: synthetic fixture",
                            raw_message={"role": "assistant", "content": "AUDIT PASS: synthetic fixture"})
                    calls = [{"id": f"call-{self.phase}", "type": "function", "function": {
                        "name": name, "arguments": json.dumps(args)}}]
                    return SimpleNamespace(tool_calls=calls, content="", raw_message={
                        "role": "assistant", "content": "", "tool_calls": calls,
                        "reasoning_content": "x" * 100_000 if self.phase == 1 else ""})

            with patch.dict(os.environ, {"FACTORY26_INLINE_SPEC_CHARS": "32000"}), patch(
                "factory26_harness.workspace_tools.run_quick_checks",
                return_value=[CheckResult("fixture", True, "mock validation only", (), 0)],
            ):
                result = CodingAgent(Model(), tools, trace, max_turns=5).implement([node])
            self.assertTrue(result.completed, result.summary)
            self.assertEqual(len(requests), 3)
            for messages in requests:
                self.assertEqual(prefilled_body(messages[1]["content"]), {"R": node.full_spec_document()})
                self.assertNotIn("[ABBREVIATED:", messages[1]["content"])
                self.assertIn("[R] Complete original", messages[1]["content"])
                self.assertLessEqual(_context_characters(messages), 96_000)
            rows = [json.loads(row) for row in trace.path.read_text().splitlines()]
            self.assertTrue(any(row["event"] == "agent_context_compacted" for row in rows))
            self.assertFalse(any(row["event"] == "tool_call" and
                row["payload"]["tool"] == "read_requirement_spec" for row in rows))
            prepared = next(row["payload"] for row in rows if row["event"] == "requirement_prefill_prepared")
            self.assertEqual(prepared["documents"][0]["characters"], len(node.full_spec_document()))
            self.assertFalse(prepared["model_receipt_confirmed"])
            self.assertGreater(prepared["duplicate_preview_characters_removed"], 1000)

    def test_mixed_prefill_removes_only_delivered_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = WorkspaceTools(root, ProductionTrace(root / ".arc/trace.jsonl"), 33245)
            nodes = [flatten_atomic({"id": key, "type": "ATOMIC", "name": key,
                "description": description, "extra_rule": "must retain exact original"})[0]
                for key, description in [("fits", "first requirement " * 30),
                                         ("too-large", "unfitted original " * 2000),
                                         ("later-fit", "third requirement " * 20)]]
            with patch.dict(os.environ, {"FACTORY26_INLINE_SPEC_CHARS": "2400"}):
                agent = CodingAgent(None, tools, tools.trace)
            with patch.object(agent, "_run", return_value=AgentRun(False, "not executed", (), 0)) as run:
                agent.implement(nodes, task_outline="preserve this architecture index")
            prompt = run.call_args.args[0]
            self.assertEqual(prefilled_body(prompt), {
                node.req_id: node.full_spec_document() for node in (nodes[0], nodes[2])})
            self.assertIn(nodes[1].compact_spec(), prompt)
            self.assertNotIn(nodes[0].compact_spec(), prompt)
            self.assertNotIn(nodes[2].compact_spec(), prompt)
            self.assertIn("preserve this architecture index", prompt)
            self.assertFalse(tools.requirement_specs_complete)
            self.assertEqual(tools.requirement_spec_offsets["too-large"], 0)

    def test_rebuild_cannot_expand_previously_measured_allocation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = WorkspaceTools(root, ProductionTrace(root / ".arc/trace.jsonl"), 33246)
            tools.register_requirement_specs({"R": "original"})
            agent = CodingAgent(None, tools, tools.trace)
            prompt = agent._prefill_prompt("original prefix", rebuild_prompt=lambda _ids: "x" * 96_000)
            self.assertTrue(prompt.startswith("original prefix"))
            self.assertEqual(prefilled_body(prompt), {"R": "original"})

    def test_opt_out_and_unfitted_documents_still_require_paging(self):
        for setting in ("0", "900"):
            with self.subTest(setting=setting), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                tools = WorkspaceTools(root, ProductionTrace(root / ".arc/trace.jsonl"), 33243)
                node = flatten_atomic({"id": "R", "type": "ATOMIC", "name": "large",
                    "description": "x" * 15_000})[0]
                with patch.dict(os.environ, {"FACTORY26_INLINE_SPEC_CHARS": setting}):
                    agent = CodingAgent(None, tools, tools.trace)
                with patch.object(agent, "_run", return_value=AgentRun(False, "not executed", (), 0)) as run:
                    agent.implement([node])
                self.assertNotIn("<untrusted_prefilled_specifications>", run.call_args.args[0])
                self.assertFalse(tools.requirement_specs_complete)

    def test_repair_session_refills_originals_on_reused_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = WorkspaceTools(root, ProductionTrace(root / ".arc/trace.jsonl"), 33244)
            tools.register_requirement_specs({"R": "exact original from previous session"})
            tools.register_inline_requirement_delivery(dict(tools.requirement_specs))
            agent = CodingAgent(None, tools, tools.trace)
            with patch.object(agent, "_run", return_value=AgentRun(False, "not executed", (), 0)) as run:
                agent.repair("synthetic startup failure", ["backend/server.mjs"])
            self.assertEqual(prefilled_body(run.call_args.args[0]), tools.requirement_specs)
            self.assertEqual(agent._initial_prefill_ids, ("R",))


if __name__ == "__main__":
    unittest.main()
