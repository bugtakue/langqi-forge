import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory26_harness.agent import _context_characters, _fit_source_snapshot, _source_snapshot


class SnapshotFittingTests(unittest.TestCase):
    def test_recovers_capacity_lost_by_first_halving_without_exceeding_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.js").write_text("export const value = 1;\n" * 1400)
            measure = lambda text: _context_characters([{"role": "user", "content": text}])
            old, old_manifest = _source_snapshot(root, ["app.js"], maximum_bytes=20_000)
            self.assertGreater(measure(old), 21_000)
            old, old_manifest = _source_snapshot(root, ["app.js"], maximum_bytes=10_000)
            snapshot, manifest = _fit_source_snapshot(root, iter(["app.js"]),
                maximum_bytes=20_000, fits=lambda text: measure(text) <= 21_000)
            self.assertLessEqual(measure(snapshot), 21_000)
            self.assertGreater(measure(snapshot), 20_700)
            self.assertGreater(manifest[0]["included_bytes"], old_manifest[0]["included_bytes"] * 1.8)
            self.assertEqual(manifest[0]["sha256"], old_manifest[0]["sha256"])
            self.assertTrue(manifest[0]["truncated"])
            self.assertIn("middle omitted", snapshot)

    def test_escaped_unicode_metadata_and_fresh_observations_stay_within_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "中文.js").write_text('const value = "文本\\\\";\n' * 1200)
            initial = {"role": "user", "content": "whole original " * 70}
            fresh = {"role": "tool", "tool_call_id": "fresh", "content": "new observation " * 70}
            measure = lambda text: _context_characters([initial, {"role": "user", "content": text}, fresh])
            with patch("factory26_harness.agent._source_snapshot", wraps=_source_snapshot) as calls:
                snapshot, manifest = _fit_source_snapshot(root, ["中文.js"], maximum_bytes=20_000,
                    fits=lambda text: measure(text) <= 8000)
            self.assertLessEqual(calls.call_count, 9)
            self.assertLessEqual(measure(snapshot), 8000)
            self.assertTrue(manifest)
            self.assertGreater(manifest[0]["included_bytes"], 0)

    def test_no_fit_and_zero_budget_do_not_claim_retained_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.js").write_text("export {};\n")
            self.assertEqual(_fit_source_snapshot(root, ["a.js"], maximum_bytes=20,
                fits=lambda _: False), ("", []))
            with patch("factory26_harness.agent._source_snapshot") as calls:
                self.assertEqual(_fit_source_snapshot(root, ["a.js"], maximum_bytes=0,
                    fits=lambda _: True), ("", []))
                calls.assert_not_called()

    def test_whole_file_fast_path_does_not_search(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = "export const ok = true;\n"
            (root / "a.js").write_text(source)
            with patch("factory26_harness.agent._source_snapshot", wraps=_source_snapshot) as calls:
                snapshot, manifest = _fit_source_snapshot(root, ["a.js"], maximum_bytes=1000,
                    fits=lambda _: True)
            self.assertEqual(calls.call_count, 1)
            self.assertIn(source, snapshot)
            self.assertFalse(manifest[0]["truncated"])
            self.assertEqual(manifest[0]["included_bytes"], len(source.encode()))


if __name__ == "__main__":
    unittest.main()
