"""Guidance stays consistent with evidence gates; no live model calls."""
import unittest
from types import SimpleNamespace

from factory26_harness.agent import _turn_budget_instruction


class TurnBudgetGuidanceTests(unittest.TestCase):
    def instruction(self, validated, recheck, *, maximum=3, verified_revision=2):
        return _turn_budget_instruction(SimpleNamespace(
            current_changes_validated=validated,
            browser_probe_requires_recheck=recheck,
            maximum_browser_probe_calls=maximum,
            browser_probe_verified_revision=verified_revision,
            change_revision=2,
        ))

    def test_unvalidated_revision_reserves_validation_before_probe(self):
        for recheck in (True, False):
            with self.subTest(recheck=recheck):
                text = self.instruction(False, recheck)
                self.assertIn("Finish edits", text)
                self.assertIn("quick validation", text)
                self.assertNotIn("finish now", text)

    def test_build_success_cannot_request_early_completion(self):
        text = self.instruction(True, True)
        self.assertIn("Run browser_probe now", text)
        self.assertIn("current-revision", text)
        self.assertIn("visible assertion", text)
        self.assertIn("Do not claim AUDIT PASS yet", text)
        self.assertNotIn("finish now", text)

    def test_never_used_probe_still_requests_first_behavioral_evidence(self):
        text = self.instruction(True, False, verified_revision=-1)
        self.assertIn("Run browser_probe now", text)
        self.assertNotIn("finish now", text)

    def test_stale_probe_revision_does_not_request_completion(self):
        text = self.instruction(True, False, verified_revision=1)
        self.assertIn("Run browser_probe now", text)

    def test_disabled_probe_does_not_request_unavailable_tool(self):
        text = self.instruction(True, False, maximum=0, verified_revision=-1)
        self.assertIn("finish now", text)
        self.assertNotIn("Run browser_probe", text)

    def test_verified_revision_still_requires_all_behaviors(self):
        text = self.instruction(True, False)
        self.assertIn("If every required behavior is implemented", text)
        self.assertIn("finish now", text)
        self.assertIn("Otherwise fix gaps", text)


if __name__ == "__main__":
    unittest.main()
