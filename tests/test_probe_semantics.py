"""Offline protocol tests; these do not claim a real browser or official pass."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from factory26_harness.agent import SYSTEM_PROMPT
from factory26_harness.browser_probe import _locator, validate_steps
from factory26_harness.trace import ProductionTrace
from factory26_harness.workspace_tools import WorkspaceTools


class ProbeSemanticsTests(unittest.TestCase):
    def test_unspecified_index_preserves_strict_role_locator(self):
        step = validate_steps([{"action": "click", "role": "link", "name": "View details"}])[0]
        page = Mock()
        target = _locator(page, step)
        self.assertNotIn("index", step)
        self.assertIs(target, page.get_by_role.return_value)
        page.get_by_role.assert_called_once_with("link", name="View details", exact=True)
        target.nth.assert_not_called()
        self.assertEqual(validate_steps([step]), [step])

    def test_explicit_repeated_item_index_is_preserved(self):
        step = validate_steps([{"action": "click", "role": "button", "name": "Edit", "index": 2}])[0]
        page = Mock()
        self.assertIs(_locator(page, step), page.get_by_role.return_value.nth.return_value)
        page.get_by_role.return_value.nth.assert_called_once_with(2)

    def test_label_and_text_are_also_strict_without_index(self):
        for step, method in (({"action": "fill", "label": "Name", "value": "Ada"}, "get_by_label"),
                             ({"action": "click", "text": "Details"}, "get_by_text")):
            with self.subTest(step=step):
                page = Mock()
                self.assertIs(_locator(page, validate_steps([step])[0]), getattr(page, method).return_value)
                getattr(page, method).return_value.nth.assert_not_called()

    def test_invalid_plan_requires_recheck_without_consuming_a_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = WorkspaceTools(root, ProductionTrace(root / "trace.jsonl"), 33143)
            tools.last_validation_passed = True
            tools.validated_revision = 0
            tools.validation_scope = "quick"
            bad = [{"action": "click", "role": "button", "name": "Save", "expect_text": list("ABCDE")}]
            with patch("factory26_harness.workspace_tools.probe_local_app") as probe:
                result = json.loads(tools.execute("browser_probe", {"steps": bad}))
                self.assertFalse(result["ok"])
                self.assertTrue(tools.browser_probe_requires_recheck)
                self.assertEqual(tools.browser_probe_calls, 0)
                probe.assert_not_called()
                probe.return_value = {"ok": True, "behavioral_checks": 1, "behavioral_assertions": 1}
                good = [{"action": "click", "role": "button", "name": "Save", "expect_text": ["Saved"]}]
                self.assertTrue(json.loads(tools.execute("browser_probe", {"steps": good}))["ok"])
                self.assertFalse(tools.browser_probe_requires_recheck)
                self.assertEqual(tools.browser_probe_calls, 1)

    def test_prompt_prioritizes_specified_roles_over_generated_controls(self):
        self.assertIn("a link must be an anchor with href", SYSTEM_PROMPT)
        self.assertIn("never adapt the probe", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
