from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from factory26_harness.qualifier import _contextual_nodes
from factory26_harness.requirements import (
    MAX_TASK_OUTLINE_CHARS,
    batches,
    flatten_atomic,
    load_requirement_tree,
    task_outline,
)


class RequirementCompilerTests(unittest.TestCase):
    def test_nonstandard_requirement_fields_are_not_silently_omitted(self) -> None:
        variants = (
            ("atomic", {"acceptance_criteria": "ATOMIC_EXTRA"}),
            ("scenario", {"scenarios": [{"name": "flow", "expected_result": "SCENARIO_EXTRA", "steps": []}]}),
            ("step", {"scenarios": [{"steps": [{"keyword": "THEN", "expected": "STEP_EXTRA"}]}]}),
        )
        for label, additions in variants:
            with self.subTest(label=label):
                tree = {
                    "id": "ROOT", "type": "FOLDER", "children": [
                        {"id": "REQ-1", "type": "ATOMIC", "description": "Ordinary body", **additions}
                    ],
                }
                node = flatten_atomic(tree)[0]
                self.assertTrue(node.is_abbreviated())
                self.assertIn("read_requirement_spec", node.compact_spec())
                self.assertIn(label.upper() + "_EXTRA", node.full_spec_document())

        tree = {
            "id": "ROOT", "type": "FOLDER", "name": "Parent",
            "release_condition": "PARENT_EXTRA",
            "children": [{"id": "REQ-1", "type": "ATOMIC", "description": "Ordinary body"}],
        }
        node = _contextual_nodes(tree, flatten_atomic(tree))[0]
        self.assertTrue(node.is_abbreviated())
        self.assertIn("read_requirement_spec", node.compact_spec())
        self.assertIn("PARENT_EXTRA", node.full_spec_document())

    def test_parent_folder_dependencies_reach_the_atomic_prompt(self) -> None:
        tree = {
            "id": "ROOT", "type": "FOLDER", "children": [
                {"id": "BASE", "type": "ATOMIC", "name": "Base"},
                {
                    "id": "GROUP", "type": "FOLDER", "name": "Grouped feature",
                    "dependencies": ["BASE"],
                    "children": [{"id": "CHILD", "type": "ATOMIC", "name": "Child"}],
                },
            ],
        }
        nodes = _contextual_nodes(tree, flatten_atomic(tree))
        child = next(node for node in nodes if node.req_id == "CHILD")
        self.assertIn("Folder dependencies: BASE", child.compact_spec())

    def test_parent_folder_dependencies_order_batches_without_hard_failure_edges(self) -> None:
        tree = {
            "id": "ROOT", "type": "FOLDER", "children": [
                {
                    "id": "LATER", "type": "FOLDER", "dependencies": ["FOUNDATION"],
                    "children": [{"id": "LATER-1", "type": "ATOMIC"}],
                },
                {
                    "id": "FOUNDATION", "type": "FOLDER",
                    "children": [
                        {"id": "BASE-1", "type": "ATOMIC"},
                        {"id": "BASE-2", "type": "ATOMIC"},
                    ],
                },
            ],
        }
        nodes = flatten_atomic(tree)
        self.assertEqual(
            [node.req_id for node in nodes], ["BASE-1", "BASE-2", "LATER-1"]
        )
        self.assertEqual(nodes[-1].dependencies, ())

    def test_cyclic_parent_folder_dependencies_fail_closed(self) -> None:
        tree = {
            "id": "ROOT", "type": "FOLDER", "children": [
                {
                    "id": "ONE", "type": "FOLDER", "dependencies": ["TWO"],
                    "children": [{"id": "ONE-1", "type": "ATOMIC"}],
                },
                {
                    "id": "TWO", "type": "FOLDER", "dependencies": ["ONE"],
                    "children": [{"id": "TWO-1", "type": "ATOMIC"}],
                },
            ],
        }
        with self.assertRaisesRegex(ValueError, "cycle"):
            flatten_atomic(tree)

    def test_abbreviated_requirement_retains_full_atomic_and_parent_details(self) -> None:
        tree = {
            "id": "ROOT",
            "name": "Parent",
            "type": "FOLDER",
            "description": "P" * 1_500 + "PARENT_END",
            "children": [{
                "id": "R-LONG",
                "type": "ATOMIC",
                "description": "D" * 21_000 + "ATOMIC_END",
                "scenarios": [{"steps": [{"keyword": "Then", "content": "S" * 1_300 + "STEP_END"}]}],
            }],
        }
        node = _contextual_nodes(tree, flatten_atomic(tree))[0]
        compact = node.compact_spec()
        self.assertNotIn("PARENT_END", compact)
        self.assertNotIn("ATOMIC_END", compact)
        self.assertNotIn("STEP_END", compact)
        self.assertTrue(node.is_abbreviated())
        self.assertIn("read_requirement_spec", compact)
        complete = node.full_spec_document()
        self.assertIn("PARENT_END", complete)
        self.assertIn("ATOMIC_END", complete)
        self.assertIn("STEP_END", complete)

    def test_many_short_scenarios_use_a_bounded_preview_without_losing_detail(self) -> None:
        node = flatten_atomic({
            "id": "ROOT", "type": "FOLDER", "children": [{
                "id": "R-MANY", "type": "ATOMIC", "description": "Several workflows",
                "scenarios": [
                    {"name": f"flow-{index}", "steps": [{"keyword": "Then", "content": "S" * 500}]}
                    for index in range(30)
                ],
            }],
        })[0]
        self.assertTrue(node.is_abbreviated())
        self.assertLess(len(node.compact_spec()), 4_000)
        self.assertNotIn("flow-29", node.compact_spec())
        self.assertIn("flow-29", node.full_spec_document())

    def test_whole_task_outline_is_bounded_and_excludes_requirement_bodies(self) -> None:
        tree = {
            "id": "ROOT",
            "name": "<untrusted> Project",
            "type": "FOLDER",
            "children": [
                {
                    "id": f"REQ-{index}",
                    "name": f"Feature {index}",
                    "type": "ATOMIC",
                    "description": "DO NOT leak this body into the index",
                    "dependencies": [f"REQ-{index - 1}"] if index else [],
                }
                for index in range(160)
            ],
        }
        nodes = flatten_atomic(tree)
        outline = task_outline(tree, nodes)
        parsed = json.loads(outline)
        self.assertLessEqual(len(outline), MAX_TASK_OUTLINE_CHARS)
        self.assertEqual(parsed["total_requirements"], 160)
        self.assertLess(parsed["listed_requirements"], 160)
        self.assertEqual(parsed["listed_requirements"], len(parsed["requirements"]))
        self.assertEqual(parsed["requirements"][1]["dependencies"], ["REQ-0"])
        self.assertNotIn("DO NOT leak", outline)
        self.assertNotIn("<untrusted>", outline)

    def test_dependency_order_is_stable(self) -> None:
        tree = {
            "id": "root",
            "type": "FOLDER",
            "children": [
                {"id": "later", "type": "ATOMIC", "dependencies": ["first"]},
                {"id": "independent", "type": "ATOMIC"},
                {"id": "first", "type": "ATOMIC"},
            ],
        }
        nodes = flatten_atomic(tree)
        self.assertEqual([node.req_id for node in nodes], ["independent", "first", "later"])

    def test_wrapped_requirement_tree_and_batches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements.yaml").write_text(
                """root:
  id: root
  type: FOLDER
  children:
    - id: one
      type: ATOMIC
    - id: two
      type: ATOMIC
    - id: three
      type: ATOMIC
""",
                encoding="utf-8",
            )
            nodes = flatten_atomic(load_requirement_tree(root))
            self.assertEqual([[node.req_id for node in group] for group in batches(nodes, 2)], [["one", "two"], ["three"]])

    def test_duplicate_unknown_and_cyclic_dependencies_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate"):
            flatten_atomic(
                {
                    "id": "root",
                    "type": "FOLDER",
                    "children": [
                        {"id": "same", "type": "ATOMIC"},
                        {"id": "same", "type": "ATOMIC"},
                    ],
                }
            )
        with self.assertRaisesRegex(ValueError, "unknown dependency"):
            flatten_atomic(
                {
                    "id": "root",
                    "type": "FOLDER",
                    "children": [
                        {
                            "id": "one",
                            "type": "ATOMIC",
                            "dependencies": ["missing"],
                        }
                    ],
                }
            )
        with self.assertRaisesRegex(ValueError, "contains a cycle"):
            flatten_atomic(
                {
                    "id": "root",
                    "type": "FOLDER",
                    "children": [
                        {"id": "one", "type": "ATOMIC", "dependencies": ["two"]},
                        {"id": "two", "type": "ATOMIC", "dependencies": ["one"]},
                    ],
                }
            )

    def test_compact_agent_spec_is_bounded(self) -> None:
        node = flatten_atomic(
            {
                "id": "root",
                "type": "FOLDER",
                "children": [
                    {
                        "id": "bounded",
                        "type": "ATOMIC",
                        "name": "N" * 5_000,
                        "description": "D" * 100_000,
                        "scenarios": [
                            {
                                "name": "scenario",
                                "steps": [
                                    {"keyword": "Then", "content": "S" * 10_000}
                                ],
                            }
                        ],
                    }
                ],
            }
        )[0]
        self.assertLess(len(node.compact_spec()), 8_500)

    def test_malformed_collection_fields_and_identifiers_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "dependencies must be an array"):
            flatten_atomic(
                {
                    "id": "root",
                    "type": "FOLDER",
                    "children": [
                        {
                            "id": "one",
                            "type": "ATOMIC",
                            "dependencies": "two",
                        }
                    ],
                }
            )
        with self.assertRaisesRegex(ValueError, "children must be an array"):
            flatten_atomic({"id": "root", "type": "FOLDER", "children": "bad"})
        with self.assertRaisesRegex(ValueError, "duplicate dependencies"):
            flatten_atomic(
                {
                    "id": "root",
                    "children": [
                        {"id": "one", "type": "ATOMIC"},
                        {
                            "id": "two",
                            "type": "ATOMIC",
                            "dependencies": ["one", "one"],
                        },
                    ],
                }
            )
        with self.assertRaisesRegex(ValueError, "control characters"):
            flatten_atomic(
                {
                    "id": "root",
                    "children": [{"id": "bad\nid", "type": "ATOMIC"}],
                }
            )
        with self.assertRaisesRegex(ValueError, "exceeds 160"):
            flatten_atomic(
                {
                    "id": "root",
                    "children": [{"id": "x" * 161, "type": "ATOMIC"}],
                }
            )

    def test_aliased_requirement_objects_are_rejected(self) -> None:
        child = {"id": "one", "type": "ATOMIC"}
        with self.assertRaisesRegex(ValueError, "cyclic or aliased"):
            flatten_atomic(
                {"id": "root", "type": "FOLDER", "children": [child, child]}
            )


if __name__ == "__main__":
    unittest.main()
