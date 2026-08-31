from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from benchmarks.run_generalization import (
    REQUIREMENTS_PATH,
    REQUIREMENTS_SHA256,
    TEST_SOURCE,
    TEST_SOURCE_SHA256,
    _locked_file,
)
from factory26_harness.requirements import (
    detect_domain,
    flatten_atomic,
    load_requirement_tree,
)
from factory26_harness.scaffold import APP_JS, INDEX_HTML, SERVER_MJS


class GeneralizationBenchmarkTests(unittest.TestCase):
    def test_change_control_is_a_locked_unseen_generic_domain(self) -> None:
        _locked_file(REQUIREMENTS_PATH, REQUIREMENTS_SHA256)
        _locked_file(TEST_SOURCE, TEST_SOURCE_SHA256)
        tree = load_requirement_tree(REQUIREMENTS_PATH)
        self.assertEqual(detect_domain(tree), "generic")
        self.assertEqual(
            {node.req_id for node in flatten_atomic(tree)},
            {"REQ-GEN-1", "REQ-GEN-2"},
        )
        self.assertNotIn(
            "Rotate signing key in the edge gateway",
            REQUIREMENTS_PATH.read_text(encoding="utf-8"),
        )
        cached_scaffold = "\n".join((INDEX_HTML, APP_JS, SERVER_MJS))
        self.assertNotIn("Change Control", cached_scaffold)
        self.assertNotIn("Reviewer must differ", cached_scaffold)

    def test_locked_input_rejects_content_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.yaml"
            path.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "locked hash"):
                _locked_file(path, "0" * 64)


if __name__ == "__main__":
    unittest.main()
