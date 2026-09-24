from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from factory26_harness.requirements import (
    MAX_TASK_OUTLINE_CHARS,
    batches,
    flatten_atomic,
    load_requirement_tree,
    task_outline,
)


class RequirementCompilerTests(unittest.TestCase):
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
