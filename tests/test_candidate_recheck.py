"""Offline boundary tests; scripted observations are not real GUI evidence."""
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from factory26_harness.regression import recheck_candidate_flows
from factory26_harness.trace import ProductionTrace, verify_trace_rows


class CandidateRecheckTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.trace = ProductionTrace(self.root / "trace.jsonl")
        self.manifest = self.enterContext(patch(
            "factory26_harness.regression.app_source_manifest",
            return_value={"frontend/src/app.js": "current-source"},
        ))
        self.probe = self.enterContext(patch(
            "factory26_harness.regression.probe_local_app",
            return_value={"ok": True, "behavioral_checks": 1, "behavioral_assertions": 1},
        ))
        self.flows = [[{"action": "click", "role": "button", "name": label,
                        "expect_text": [f"Saved {label}"]}] for label in ("New success", "New rejection")]

    def check(self, flows=None):
        return recheck_candidate_flows(self.root, 3907, self.flows if flows is None else flows, self.trace)

    def rows(self):
        return [json.loads(line) for line in self.trace.path.read_text().splitlines()]

    def test_replays_each_original_separately_and_never_stores_promoted_capsules(self):
        original = deepcopy(self.flows)
        def observed(root, port, steps):
            steps[0]["name"] = "mutated by probe fixture"
            return {"ok": True, "behavioral_checks": 1, "behavioral_assertions": 1}
        self.probe.side_effect = observed
        self.assertTrue(self.check().passed)
        self.assertEqual(self.flows, original)
        self.assertEqual(self.probe.call_count, 2)
        rows = self.rows()
        self.assertEqual([row["event"] for row in rows], ["candidate_behavior_recheck"])
        self.assertEqual(rows[0]["payload"]["status"], "passed")
        self.assertIsNotNone(rows[0]["payload"]["source_manifest_digest"])
        verify_trace_rows(rows)

    def test_failure_does_not_erase_other_recipe_or_publish_success(self):
        self.probe.side_effect = [
            {"ok": False, "assertion_failures": [{"missing": ["New success"]}]},
            {"ok": True, "behavioral_checks": 1, "behavioral_assertions": 1},
        ]
        self.assertFalse(self.check().passed)
        payload = self.rows()[-1]["payload"]
        self.assertEqual(payload["status"], "failed")
        self.assertEqual([item["passed"] for item in payload["results"]], [False, True])

    def test_empty_is_explicit_no_coverage_without_browser_or_manifest_read(self):
        self.assertTrue(self.check([]).passed)
        self.assertEqual(self.rows()[-1]["payload"]["status"], "no_coverage")
        self.probe.assert_not_called()
        self.manifest.assert_not_called()

    def test_invalid_or_excessive_recipes_fail_before_any_launch(self):
        for flows in ([[]], self.flows * 3, [[{"action": "navigate", "path": "https://example.com"}]]):
            with self.subTest(flows=flows):
                self.assertFalse(self.check(flows).passed)
        self.probe.assert_not_called()

    def test_source_failure_cannot_pass(self):
        self.manifest.side_effect = ValueError("source is unavailable")
        self.assertFalse(self.check().passed)
        self.probe.assert_not_called()

    def test_exception_and_invalid_observations_fail_closed(self):
        for observed in (None, {}, {"ok": True},
                         {"ok": True, "behavioral_checks": True, "behavioral_assertions": 1},
                         {"ok": True, "behavioral_checks": 1, "behavioral_assertions": 1, "page_errors": ["error"]}):
            with self.subTest(observed=observed):
                self.probe.return_value = observed
                self.assertFalse(self.check().passed)
        self.probe.side_effect = RuntimeError("launch failed")
        self.assertFalse(self.check().passed)


if __name__ == "__main__":
    unittest.main()
