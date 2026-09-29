"""The run contract keeps graph order, names the loop, and keeps unedited scaffolds out."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from factory26_harness.architecture import (
    CONTEXT_SECTIONS,
    HARNESS_GATES,
    LAYERS,
    LOOP_STATES,
    describe_run,
    loop_phase,
)
from factory26_harness.requirements import flatten_atomic, load_requirement_tree


ROOT = Path(__file__).resolve().parents[1]


class ArchitectureContractTest(unittest.TestCase):
    def test_layers_and_gates_are_the_run_contract(self) -> None:
        self.assertEqual(LAYERS, ("graph", "context", "loop", "harness"))
        self.assertIn("task_outline", CONTEXT_SECTIONS)
        self.assertIn("prior_batch_handoffs", CONTEXT_SECTIONS)
        self.assertIn("audit_pass", LOOP_STATES)
        self.assertIn("stall", LOOP_STATES)
        self.assertIn("refuse_unedited_scaffold", HARNESS_GATES)
        self.assertIn("dependency_block", HARNESS_GATES)

    def test_dependency_scheduled_first(self) -> None:
        tree = {
            "id": "root",
            "type": "FOLDER",
            "children": [
                {"id": "later", "type": "ATOMIC", "dependencies": ["first"]},
                {"id": "first", "type": "ATOMIC"},
            ],
        }
        nodes = flatten_atomic(tree)
        plan = describe_run(
            tree, nodes, batch_size=1, batch_spec_chars=32000,
            max_turns=20, repair_rounds=2,
        )
        self.assertEqual(plan.requirement_ids, ("first", "later"))
        record = plan.public_record()
        self.assertEqual(record["graph"]["batches"], [["first"], ["later"]])
        self.assertTrue(record["context"]["outline_covers_every_requirement"])
        self.assertEqual(record["loop"]["acceptance_prefix"], "AUDIT PASS")
        self.assertTrue(record["harness"]["keeps_only_checked_edits"])

    def test_reversed_dependency_is_rejected(self) -> None:
        tree = {
            "id": "root",
            "type": "FOLDER",
            "children": [
                {"id": "later", "type": "ATOMIC", "dependencies": ["first"]},
                {"id": "first", "type": "ATOMIC"},
            ],
        }
        nodes = list(reversed(flatten_atomic(tree)))
        with self.assertRaisesRegex(ValueError, "scheduled before"):
            describe_run(
                tree, nodes, batch_size=2, batch_spec_chars=32000,
                max_turns=20, repair_rounds=0,
            )

    def test_current_batch_graph_splits_inside_and_earlier_edges(self) -> None:
        from factory26_harness.architecture import current_batch_graph
        from factory26_harness.requirements import RequirementNode

        later = RequirementNode(
            req_id="later", name="Later", description="d",
            dependencies=("first", "also"), scenarios=(), visual_reference=(), raw={},
        )
        also = RequirementNode(
            req_id="also", name="Also", description="d",
            dependencies=(), scenarios=(), visual_reference=(), raw={},
        )
        encoded = current_batch_graph([also, later], accepted_ids=["first", "first"])
        payload = json.loads(encoded)
        self.assertEqual(payload["implement_only"], ["also", "later"])
        self.assertEqual(payload["accepted_requirement_ids"], ["first"])
        self.assertEqual(payload["edges"][1]["dependencies_in_batch"], ["also"])
        self.assertEqual(payload["edges"][1]["dependencies_already_scheduled"], ["first"])
        self.assertNotIn("<", encoded)

    def test_repair_prompt_keeps_the_batch_graph(self) -> None:
        from factory26_harness.agent import CodingAgent
        from factory26_harness.requirements import RequirementNode
        from factory26_harness.trace import ProductionTrace
        from factory26_harness.workspace_tools import WorkspaceTools

        captured: list[str] = []

        class CaptureModel:
            def complete(self, messages, _tools):
                captured.append(messages[1]["content"])
                from types import SimpleNamespace
                return SimpleNamespace(
                    raw_message={"role": "assistant", "content": ""},
                    tool_calls=(),
                    content="",
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = ProductionTrace(root / "trace.jsonl")
            node = RequirementNode(
                req_id="later", name="Later", description="d",
                dependencies=("first",), scenarios=(), visual_reference=(), raw={},
            )
            CodingAgent(CaptureModel(), WorkspaceTools(root, trace, 3991), trace, max_turns=2).repair(
                "startup failed",
                ["backend/server.mjs"],
                nodes=[node],
                task_outline='{"requirements":[{"id":"later"}]}',
                accepted_ids=["first"],
            )
        self.assertIn("<untrusted_batch_graph>", captured[0])
        self.assertIn("<untrusted_task_outline>", captured[0])
        self.assertIn('"dependencies_already_scheduled":["first"]', captured[0])
        self.assertIn("backend/server.mjs", captured[0])

    def test_loop_phase_follows_the_edit_gate(self) -> None:
        self.assertEqual(loop_phase(
            edited=False, validated=False, probe_current=False,
            audit_for_revision=False, empty_turns=0,
        ), "read_or_edit")
        self.assertEqual(loop_phase(
            edited=True, validated=False, probe_current=False,
            audit_for_revision=False, empty_turns=0,
        ), "quick_validation")
        self.assertEqual(loop_phase(
            edited=True, validated=True, probe_current=False,
            audit_for_revision=False, empty_turns=1,
        ), "browser_probe")
        self.assertEqual(loop_phase(
            edited=True, validated=True, probe_current=True,
            audit_for_revision=False, empty_turns=2,
        ), "acceptance_audit")
        self.assertEqual(loop_phase(
            edited=True, validated=True, probe_current=True,
            audit_for_revision=True, empty_turns=0,
        ), "audit_pass")
        self.assertEqual(loop_phase(
            edited=True, validated=True, probe_current=True,
            audit_for_revision=True, empty_turns=3,
        ), "stall")

    def test_public_tasks_keep_a_complete_graph_index(self) -> None:
        tasks = (
            ROOT / "docs/evidence/conductor-20260928/canvas-public-source/hackathon--github",
            ROOT / "docs/evidence/sheet-requirements-20260929.yaml",
        )
        for path in tasks:
            tree = load_requirement_tree(path)
            nodes = flatten_atomic(tree)
            plan = describe_run(
                tree, nodes, batch_size=4, batch_spec_chars=32000,
                max_turns=20, repair_rounds=2,
            )
            record = plan.public_record()
            self.assertEqual(record["graph"]["requirement_count"], len(nodes))
            self.assertTrue(record["context"]["outline_covers_every_requirement"], path.name)
            self.assertEqual(
                [req_id for batch in record["graph"]["batches"] for req_id in batch],
                [node.req_id for node in nodes],
            )
            self.assertLessEqual(record["graph"]["batch_count"], 12 if "github" in path.name or path.parent.name.endswith("github") else 8)

    def test_shared_folder_context_keeps_siblings_in_one_batch(self) -> None:
        tree = {
            "id": "ROOT",
            "name": "Module",
            "type": "FOLDER",
            "description": "shared " * 800,
            "children": [
                {"id": f"R-{index}", "type": "ATOMIC", "description": "body " * 40}
                for index in range(4)
            ],
        }
        nodes = flatten_atomic(tree)
        from factory26_harness.qualifier import _contextual_nodes
        contextual = _contextual_nodes(tree, nodes)
        shared = describe_run(
            tree, contextual, batch_size=4, batch_spec_chars=12000,
            max_turns=20, repair_rounds=0,
        )
        separate = __import__(
            "factory26_harness.requirements", fromlist=["batches"]
        ).batches(contextual, 4, max_spec_chars=12000)
        self.assertEqual(len(shared.groups), 1)
        self.assertGreater(len(separate), 1)

    def test_first_github_batch_originals_fit_in_one_prompt(self) -> None:
        from unittest.mock import patch

        from factory26_harness.agent import AgentRun, CodingAgent
        from factory26_harness.qualifier import _contextual_nodes
        from factory26_harness.trace import ProductionTrace
        from factory26_harness.workspace_tools import WorkspaceTools

        path = ROOT / "docs/evidence/conductor-20260928/canvas-public-source/hackathon--github"
        tree = load_requirement_tree(path)
        nodes = _contextual_nodes(tree, flatten_atomic(tree))
        plan = describe_run(
            tree, nodes, batch_size=4, batch_spec_chars=32000,
            max_turns=20, repair_rounds=2,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = ProductionTrace(root / "trace.jsonl")
            agent = CodingAgent(None, WorkspaceTools(root, trace, 4001), trace, max_turns=2)
            with patch.object(agent, "_run", return_value=AgentRun(False, "not executed", (), 0)) as run:
                agent.implement(list(plan.groups[0]), task_outline=plan.outline)
        prompt = run.call_args.args[0]
        self.assertEqual(
            agent._initial_prefill_ids,
            ("REQ-1-1-1", "REQ-1-1-2", "REQ-1-1-3", "REQ-1-2"),
        )
        self.assertLessEqual(len(prompt), 96_000)
        for req_id in agent._initial_prefill_ids:
            self.assertIn(f"[{req_id}] Complete original", prompt)


if __name__ == "__main__":
    unittest.main()
