"""Bounded semantic-state probe fixtures; no live model/browser or task solutions."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from factory26_harness.browser_probe import (
    MAX_ASSERTIONS, CONTROL_PROPERTIES, _control_result, _observe_probe_step,
    _observation_failures, _page_observation, _settled_observation,
    control_expectation_schema, validate_steps,
)
from factory26_harness.trace import ProductionTrace, verify_trace_rows
from factory26_harness.workspace_tools import MAX_TOOL_RESULT_CHARS, WorkspaceTools


def expectation(prop="selected", expected=True):
    return {"role": "tab", "name": "Details", "property": prop, "equals": expected}


def page_fixture(attributes=None, value="", disabled=False, checked=False):
    page = MagicMock(url="http://127.0.0.1:3917/detail")
    target = page.get_by_role.return_value
    target.count.return_value = 1
    target.is_visible.return_value = True
    target.get_attribute.side_effect = lambda key, **_: (attributes or {}).get(key)
    target.input_value.return_value = value
    target.is_disabled.return_value = disabled
    target.is_checked.return_value = checked
    page.get_by_label.return_value = target
    page.locator.return_value.inner_text.return_value = "Ready"
    page.evaluate.return_value = []
    return page, target


class ControlAssertionTests(unittest.TestCase):
    def test_validation_schema_and_existing_plan_shape(self):
        old = validate_steps([{"action": "reload", "expect_text": ["Ready"]}])[0]
        self.assertNotIn("expect_controls", old)
        assertions = [expectation(expected=False), {"label": "Name", "property": "value", "equals": "",
                       "scope": {"role": "dialog", "name": "Edit"}}]
        step = validate_steps([{"action": "reload", "expect_controls": assertions}])[0]
        self.assertEqual(step["expect_controls"], assertions)
        self.assertEqual(control_expectation_schema()["maxItems"], MAX_ASSERTIONS)
        self.assertEqual(control_expectation_schema()["items"]["properties"]["property"]["enum"],
                         list(CONTROL_PROPERTIES))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = WorkspaceTools(root, ProductionTrace(root / "trace.jsonl"), 3917)
            schema = next(s for s in tools.schemas() if s["function"]["name"] == "browser_probe")
            self.assertEqual(schema["function"]["parameters"]["properties"]["steps"]["items"]
                             ["properties"]["expect_controls"], control_expectation_schema())

    def test_invalid_or_executable_assertions_fail_before_browser_launch(self):
        invalid = [None, [], {**expectation(), "selector": "#x"}, {**expectation(), "label": "Details"},
                   {**expectation(), "property": "onclick"}, expectation(expected="false"),
                   expectation("value", True), expectation("value", "x" * 501),
                   {**expectation(), "role": {}}, {"label": "", "property": "value", "equals": ""},
                   {**expectation(), "scope": {"role": "button"}}]
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(ValueError):
                validate_steps([{"action": "reload", "expect_controls": [item]}])
        for assertions in ({}, [expectation()] * (MAX_ASSERTIONS + 1)):
            with self.assertRaises(ValueError):
                validate_steps([{"action": "reload", "expect_controls": assertions}])

    def test_text_success_does_not_mask_wrong_selected_state(self):
        page, target = page_fixture({"aria-selected": "false"})
        observed = _page_observation(page, expected=["Ready"], absent=[], expect_controls=[expectation()])
        self.assertEqual(observed["missing_text"], [])
        self.assertEqual(observed["control_results"][0]["actual"], False)
        self.assertFalse(observed["control_results"][0]["matched"])
        failures = _observation_failures([observed])
        self.assertIn("Control selected mismatch", failures[0]["missing"][0])
        self.assertIn('"name": "Details"', failures[0]["missing"][0])
        page.get_by_role.assert_called_once_with("tab", name="Details", exact=True)
        target.click.assert_not_called()

    def test_missing_or_invalid_aria_state_is_not_false(self):
        for attributes in ({}, {"aria-selected": "mixed"}, {"aria-checked": "mixed"}):
            prop = "checked" if "aria-checked" in attributes else "selected"
            page, _ = page_fixture(attributes)
            result = _control_result(page, expectation(prop, False))
            self.assertIsNone(result["actual"])
            self.assertFalse(result["matched"])

    def test_exact_input_empty_native_checked_and_disabled_values(self):
        cases = [({}, "value", "", "", False, False),
                 ({}, "value", "=SUM(A1:A2)", "=SUM(A1:A2)", False, False),
                 ({}, "checked", True, "", False, True),
                 ({"aria-checked": "true"}, "checked", True, "", False, False),
                 ({}, "disabled", True, "", True, False),
                 ({"aria-selected": "false"}, "selected", False, "", False, False)]
        for attributes, prop, expected, value, disabled, checked in cases:
            with self.subTest(prop=prop, expected=expected):
                page, _ = page_fixture(attributes, value, disabled, checked)
                self.assertTrue(_control_result(page, expectation(prop, expected))["matched"])

    def test_password_value_never_read_and_long_values_cannot_prefix_match(self):
        for kind in ("password", "PASSWORD"):
            page, target = page_fixture({"type": kind}, "never-read")
            result = _control_result(page, expectation("value", "x"))
            self.assertFalse(result["matched"])
            target.input_value.assert_not_called()
            self.assertNotIn("never-read", json.dumps(result))
        page, _ = page_fixture(value="x" * 501)
        result = _control_result(page, expectation("value", "x" * 500))
        self.assertFalse(result["matched"])
        self.assertEqual(len(result["actual"]), 500)

    def test_missing_ambiguous_or_hidden_controls_fail_without_reading_value(self):
        for count, visible in ((0, True), (2, True), (1, False)):
            page, target = page_fixture()
            target.count.return_value = count
            target.is_visible.return_value = visible
            result = _control_result(page, expectation("value", ""))
            self.assertFalse(result["matched"])
            target.input_value.assert_not_called()

    def test_assertion_scope_is_independent_of_action_scope(self):
        page, target = page_fixture({"aria-selected": "true"})
        owner = MagicMock()
        owner.count.return_value = 1
        owner.get_by_role.return_value = target
        page.get_by_role.side_effect = lambda role, **_: owner if role == "dialog" else target
        assertion = {**expectation(), "scope": {"role": "dialog", "name": "Edit"}}
        result = _control_result(page, assertion)
        self.assertTrue(result["matched"])
        page.get_by_role.assert_called_once_with("dialog", exact=True, name="Edit")
        owner.get_by_role.assert_called_once_with("tab", name="Details", exact=True)

    def test_settle_waits_for_control_state_not_only_visible_text(self):
        page, _ = page_fixture()
        base = {"missing_text": [], "unexpected_text": [], "visible_text": "Ready"}
        with patch("factory26_harness.browser_probe._page_observation", side_effect=[
            {**base, "control_failures": ["selected mismatch"]}, {**base, "control_failures": []}
        ]) as observe:
            result = _settled_observation(page, expected=["Ready"], absent=[], expect_controls=[expectation()])
        self.assertEqual(observe.call_count, 2)
        self.assertEqual(result["control_failures"], [])
        page.wait_for_timeout.assert_called_once_with(100)

    def test_action_origin_guard_precedes_control_state_read(self):
        page, target = page_fixture()
        page.url = "https://example.test/private"
        step = validate_steps([{"action": "reload", "expect_controls": [expectation()]}])[0]
        with patch("factory26_harness.browser_probe._perform"):
            result = _observe_probe_step(page, step, "http://127.0.0.1:3917")
        self.assertIn("execution_error", result)
        page.get_by_role.assert_not_called()
        target.get_attribute.assert_not_called()

    def test_mismatch_remains_failure_after_compaction_and_sealed_trace(self):
        page, _ = page_fixture({"aria-selected": "false"})
        observed = _page_observation(page, expected=["Ready"], absent=[], expect_controls=[expectation()])
        result = {"ok": False, "workspace_isolated": True, "behavioral_checks": 1,
                  "behavioral_assertions": 1, "assertion_failures": _observation_failures([observed]),
                  "observations": [{**observed, "visible_text": "old " * 4000}, observed]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = ProductionTrace(root / "trace.jsonl")
            tools = WorkspaceTools(root, trace, 3917)
            tools.last_validation_passed = True
            tools.validated_revision = 0
            tools.validation_scope = "quick"
            with patch("factory26_harness.workspace_tools.probe_local_app", return_value=result):
                encoded = tools.execute("browser_probe", {"steps": [
                    {"action": "reload", "expect_controls": [expectation()]}]})
            output = json.loads(encoded)
            self.assertLessEqual(len(encoded), MAX_TOOL_RESULT_CHARS)
            self.assertTrue(output["truncated"])
            self.assertFalse(output["ok"])
            self.assertIn("selected", json.dumps(output["assertion_failures"]))
            self.assertTrue(tools.browser_probe_requires_recheck)
            self.assertEqual(tools.verified_browser_flows, [])
            rows = [json.loads(line) for line in trace.path.read_text().splitlines()]
            self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])

    def test_isolated_runner_counts_state_assertions_and_includes_them_in_failure_gate(self):
        from tests.test_probe_failure_scene import ProbeFailureSceneTests
        steps = validate_steps([{"action": "reload", "expect_controls": [expectation()]}])
        for selected in ("true", "false"):
            with self.subTest(selected=selected):
                page, _ = page_fixture({"aria-selected": selected})
                observed = _page_observation(page, expected=[], absent=[], expect_controls=[expectation()])
                result, calls = ProbeFailureSceneTests()._run_fixture([observed], steps)
                self.assertEqual(calls, 1)
                self.assertEqual(result["behavioral_assertions"], 1)
                self.assertEqual(result["ok"], selected == "true")
                self.assertEqual(len(result["assertion_failures"]), int(selected != "true"))

    def test_state_assertions_augment_positive_interaction_recipes_for_independent_replay(self):
        from factory26_harness.regression import RegressionMemory, _recipe
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = WorkspaceTools(root, ProductionTrace(root / "trace.jsonl"), 3917)
            tools.last_validation_passed = True
            tools.validated_revision = 0
            tools.validation_scope = "quick"
            steps = [{"action": "click", "role": "button", "name": "Save", "expect_text": ["Ready"],
                      "expect_controls": [expectation(expected=False)]}]
            with patch("factory26_harness.workspace_tools.probe_local_app", return_value={
                "ok": True, "behavioral_checks": 1, "behavioral_assertions": 1
            }):
                result = json.loads(tools.execute("browser_probe", {"steps": steps}))
            self.assertTrue(result["ok"])
            self.assertFalse(tools.browser_probe_requires_recheck)
            retained = tools.verified_browser_flows
            self.assertEqual(retained[0], validate_steps(steps))
            self.assertEqual(_recipe(retained[0]), validate_steps(steps))
            manifest = {"frontend/src/app.js": "fixture-source"}
            memory = RegressionMemory(tools.trace)
            self.assertTrue(memory.remember(["R"], retained[0], manifest))
            with patch("factory26_harness.regression.app_source_manifest", return_value=manifest), \
                 patch("factory26_harness.regression.probe_local_app", return_value={
                     "ok": True, "behavioral_checks": 1, "behavioral_assertions": 2}) as replay:
                self.assertTrue(memory.check(root, 3917, final=True).passed)
            self.assertEqual(replay.call_args.args[2], validate_steps(steps))
            retained[0][0]["expect_controls"][0]["equals"] = True
            self.assertFalse(tools.verified_browser_flows[0][0]["expect_controls"][0]["equals"])
            # Preserve the existing capsule gate: an interaction plus positive
            # literal text is still required; state assertions are supplementary.
            with self.assertRaises(ValueError):
                _recipe([{k: v for k, v in steps[0].items() if k != "expect_text"}])


if __name__ == "__main__":
    unittest.main()
