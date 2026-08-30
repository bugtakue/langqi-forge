from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from factory26_harness.requirements import batches, flatten_atomic, load_requirement_tree


class RequirementCompilerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
