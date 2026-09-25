from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from factory26_harness.browser_probe import (
    SCOPE_ROLES, _locator, _page_observation, _settled_observation, validate_steps,
)
from factory26_harness.regression import RegressionMemory
from factory26_harness.trace import ProductionTrace
from factory26_harness.workspace_tools import WorkspaceTools


class BrowserScopeTests(unittest.TestCase):
    def test_scope_validation_is_bounded_and_copy_safe(self) -> None:
        raw = {"action": "click", "role": "button", "name": "Save",
               "scope": {"role": "dialog", "name": "Edit record"},
               "expect_scope": {"role": "region", "name": "Record"},
               "expect_text": ["Saved"]}
        result = validate_steps([raw])[0]
        raw["scope"]["name"] = "mutated"
        raw["expect_scope"]["name"] = "mutated"
        self.assertEqual(result["scope"]["name"], "Edit record")
        self.assertEqual(result["expect_scope"]["name"], "Record")
        reload_step = validate_steps([{
            "action": "reload", "expect_scope": {"role": "main"}, "expect_text": ["Saved"],
        }])[0]
        self.assertEqual(reload_step["expect_scope"], {"role": "main"})

    def test_invalid_scopes_are_rejected_not_silently_dropped(self) -> None:
        invalid = [None, [], "main", {}, {"role": "button"}, {"role": True},
                   {"role": "main", "selector": "#private"},
                   {"role": "main", "index": 0}, {"role": "main", "name": ""},
                   {"role": "main", "name": 4}, {"role": "main", "name": "x" * 201},
                   {"role": "main", "name": "x\ny"}]
        for scope in invalid:
            for key in ("scope", "expect_scope"):
                with self.subTest(scope=scope, key=key), self.assertRaises(ValueError):
                    validate_steps([{"action": "click", "text": "Save", key: scope,
                                     "expect_text": ["Saved"]}])
        for step in (
            {"action": "reload", "scope": {"role": "main"}},
            {"action": "navigate", "path": "/", "scope": {"role": "main"}},
            {"action": "click", "text": "Save", "expect_scope": {"role": "main"}},
        ):
            with self.subTest(step=step), self.assertRaises(ValueError):
                validate_steps([step])

    def test_action_scopes_before_resolving_the_child_and_preserves_strictness(self) -> None:
        page = MagicMock()
        owner = page.get_by_role.return_value
        owner.count.return_value = 1
        target = _locator(page, {"role": "link", "name": "Sign in", "scope": {"role": "main"}})
        page.get_by_role.assert_called_once_with("main", exact=True)
        owner.wait_for.assert_called_once_with(state="visible", timeout=5000)
        owner.get_by_role.assert_called_once_with("link", name="Sign in", exact=True)
        self.assertIs(target, owner.get_by_role.return_value)
        target.nth.assert_not_called()
        for method in ("first", "last"):
            getattr(owner, method).assert_not_called()

    def test_ambiguous_or_missing_container_does_not_select_any_child(self) -> None:
        for error in ("strict mode violation", "owner not visible"):
            with self.subTest(error=error):
                page = MagicMock()
                owner = page.get_by_role.return_value
                owner.wait_for.side_effect = RuntimeError(error)
                with self.assertRaisesRegex(RuntimeError, error):
                    _locator(page, {"label": "Name", "scope": {"role": "form", "name": "Edit"}})
                owner.get_by_label.assert_not_called()

    def test_intentional_item_index_is_within_named_owner_only(self) -> None:
        page = MagicMock()
        owner = page.get_by_role.return_value
        owner.count.return_value = 1
        result = _locator(page, {"text": "Open", "index": 1,
                                 "scope": {"role": "region", "name": "Recent records"}})
        page.get_by_role.assert_called_once_with("region", name="Recent records", exact=True)
        owner.get_by_text.assert_called_once_with("Open", exact=True)
        owner.get_by_text.return_value.nth.assert_called_once_with(1)
        self.assertIs(result, owner.get_by_text.return_value.nth.return_value)

    def test_unscoped_locator_keeps_existing_behavior(self) -> None:
        page = MagicMock()
        result = _locator(page, {"label": "Name"})
        page.get_by_label.assert_called_once_with("Name", exact=True)
        page.get_by_role.assert_not_called()
        self.assertIs(result, page.get_by_label.return_value)

    def test_global_success_cannot_satisfy_local_feedback(self) -> None:
        page = MagicMock()
        page.url = "http://127.0.0.1:3000/records"
        page.locator.return_value.inner_text.return_value = "Saved\nEdit record\nPending"
        owner = page.get_by_role.return_value
        owner.count.return_value = 1
        owner.inner_text.return_value = "Edit record\nPending"
        with patch("factory26_harness.browser_probe._controls", return_value=[]):
            scoped = _page_observation(page, expected=["Saved"], absent=["Pending"],
                                       expect_scope={"role": "form", "name": "Edit record"})
            global_result = _page_observation(page, expected=["Saved"], absent=[])
        self.assertEqual(scoped["missing_text"], ["Saved"])
        self.assertEqual(scoped["unexpected_text"], ["Pending"])
        self.assertEqual(scoped["assertion_text"], "Edit record\nPending")
        self.assertEqual(scoped["assertion_scope"], {"role": "form", "name": "Edit record"})
        self.assertEqual(global_result["missing_text"], [])
        self.assertNotIn("assertion_scope", global_result)
        owner.wait_for.assert_called_once_with(state="visible", timeout=4000)

    def test_missing_owner_cannot_pass_absence_assertion(self) -> None:
        page = MagicMock()
        page.locator.return_value.inner_text.return_value = "Unrelated page"
        page.get_by_role.return_value.wait_for.side_effect = RuntimeError("owner missing")
        with self.assertRaisesRegex(RuntimeError, "owner missing"):
            _page_observation(page, expected=[], absent=["Error"], expect_scope={"role": "main"})

    def test_explicit_count_guard_rejects_ambiguous_wait_implementations(self) -> None:
        for count in (0, 2):
            with self.subTest(count=count):
                page = MagicMock()
                owner = page.get_by_role.return_value
                owner.count.return_value = count
                # Even when a wait implementation does not enforce uniqueness,
                # we must not select the only matching child of two owners.
                with self.assertRaisesRegex(RuntimeError, "exactly one"):
                    _locator(page, {"role": "button", "name": "Inspect first",
                                    "scope": {"role": "region", "name": "Repeated owner"}})
                owner.get_by_role.assert_not_called()
                with self.assertRaisesRegex(RuntimeError, "exactly one"):
                    _page_observation(page, expected=[], absent=["Error"],
                                      expect_scope={"role": "region", "name": "Repeated owner"})
                owner.inner_text.assert_not_called()

    def test_async_settle_rechecks_the_same_owner(self) -> None:
        pending = {"missing_text": ["Saved"], "unexpected_text": [], "visible_text": "Pending"}
        passed = {"missing_text": [], "unexpected_text": [], "visible_text": "Saved"}
        page = MagicMock()
        with patch("factory26_harness.browser_probe._page_observation",
                   side_effect=[pending, passed]) as observe:
            result = _settled_observation(page, expected=["Saved"], absent=[],
                                          expect_scope={"role": "region", "name": "Record"})
        self.assertIs(result, passed)
        self.assertEqual(observe.call_count, 2)
        for call in observe.call_args_list:
            self.assertEqual(call.kwargs["expect_scope"], {"role": "region", "name": "Record"})

    def test_schema_matches_validation_and_invalid_scope_costs_no_launch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = WorkspaceTools(root, ProductionTrace(root / "trace.jsonl"), 3991)
            tools.last_validation_passed = True
            tools.validated_revision = 0
            tools.validation_scope = "quick"
            schema = next(item["function"] for item in tools.schemas()
                          if item["function"]["name"] == "browser_probe")
            fields = schema["parameters"]["properties"]["steps"]["items"]["properties"]
            for key in ("scope", "expect_scope"):
                self.assertEqual(fields[key]["properties"]["role"]["enum"], list(SCOPE_ROLES))
                self.assertFalse(fields[key]["additionalProperties"])
            with patch("factory26_harness.workspace_tools.probe_local_app") as probe:
                result = json.loads(tools.execute("browser_probe", {"steps": [
                    {"action": "click", "text": "Save", "scope": {"role": "main", "index": 0}},
                ]}))
            self.assertFalse(result["ok"])
            self.assertEqual(tools.browser_probe_calls, 0)
            probe.assert_not_called()

    def test_regression_capsule_retains_action_and_assertion_owners(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory = RegressionMemory(ProductionTrace(root / "trace.jsonl"))
            steps = [{"action": "click", "role": "button", "name": "Save",
                      "scope": {"role": "dialog", "name": "Edit record"},
                      "expect_scope": {"role": "region", "name": "Record"},
                      "expect_text": ["Saved"]}]
            manifest = {"frontend/src/app.js": "source-a"}
            self.assertTrue(memory.remember(["REQ-fixture"], steps, manifest))
            with patch("factory26_harness.regression.app_source_manifest", return_value=manifest), patch(
                "factory26_harness.regression.probe_local_app",
                return_value={"ok": True, "behavioral_checks": 1, "behavioral_assertions": 1},
            ) as probe:
                self.assertTrue(memory.check(root, 3991, final=True).passed)
                self.assertEqual(probe.call_args.args[2], validate_steps(steps))
                probe.return_value = {"ok": False, "assertion_failures": [{"missing": ["Saved"]}]}
                self.assertFalse(memory.check(root, 3991, final=True).passed)


if __name__ == "__main__":
    unittest.main()
