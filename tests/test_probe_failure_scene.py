"""Offline page/process fixtures; no browser or model is launched."""
import contextlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from factory26_harness.browser_probe import (
    _observe_probe_step, _probe_isolated_app, validate_steps,
)
from factory26_harness.trace import ProductionTrace, verify_trace_rows
from factory26_harness.workspace_tools import MAX_TOOL_RESULT_CHARS, WorkspaceTools


def scene(text="Create record"):
    return {"path": "/new", "visible_text": text, "visible_text_truncated": False,
            "controls": [{"tag": "input", "role": "", "name": "Record name", "disabled": False}],
            "missing_text": [], "unexpected_text": []}


class ProbeFailureSceneTests(unittest.TestCase):
    def test_locator_timeout_returns_local_scene_without_retry_or_assertion_pass(self):
        page = MagicMock(url="http://127.0.0.1:3917/new")
        step = validate_steps([{"action": "fill", "label": "Name", "value": "Fixture",
                                "expect_text": ["Saved"]}])[0]
        with patch("factory26_harness.browser_probe._perform", side_effect=TimeoutError("missing label")) as action, \
             patch("factory26_harness.browser_probe._page_observation", return_value=scene()) as observe:
            result = _observe_probe_step(page, step, "http://127.0.0.1:3917")
        self.assertEqual(action.call_count, 1)
        observe.assert_called_once_with(page, expected=[], absent=[])
        self.assertEqual(result["controls"][0]["name"], "Record name")
        self.assertEqual(result["execution_error"]["type"], "TimeoutError")
        self.assertTrue(result["observation_only"])

    def test_missing_scope_is_not_reused_for_failure_scene(self):
        page = MagicMock(url="http://127.0.0.1:3917/new")
        step = validate_steps([{"action": "reload", "expect_text": ["Saved"],
                                "expect_scope": {"role": "dialog", "name": "Create"}}])[0]
        with patch("factory26_harness.browser_probe._perform"), \
             patch("factory26_harness.browser_probe._settled_observation", side_effect=RuntimeError("scope gone")), \
             patch("factory26_harness.browser_probe._page_observation", return_value=scene()) as observe:
            result = _observe_probe_step(page, step, "http://127.0.0.1:3917")
        observe.assert_called_once_with(page, expected=[], absent=[])
        self.assertEqual(result["execution_error"]["message"], "scope gone")

    def test_external_origin_never_read_even_if_action_throws(self):
        for url in ("https://example.test/private", "http://127.0.0.1:4000/private", "file:///private"):
            with self.subTest(url=url):
                page = MagicMock(url=url)
                step = validate_steps([{"action": "reload"}])[0]
                with patch("factory26_harness.browser_probe._perform", side_effect=TimeoutError("navigation failed")), \
                     patch("factory26_harness.browser_probe._page_observation") as observe:
                    result = _observe_probe_step(page, step, "http://127.0.0.1:3917")
                observe.assert_not_called()
                self.assertNotIn("visible_text", result)
                self.assertIn("outside", result["snapshot_unavailable"])

    def test_failed_snapshot_does_not_replace_original_error(self):
        page = MagicMock(url="http://127.0.0.1:3917/new")
        with patch("factory26_harness.browser_probe._perform", side_effect=TimeoutError("x" * 2000)), \
             patch("factory26_harness.browser_probe._page_observation", side_effect=RuntimeError("closed")):
            result = _observe_probe_step(page, {"action": "reload"}, "http://127.0.0.1:3917")
        self.assertEqual(result["execution_error"], {"type": "TimeoutError", "message": "x" * 1000})
        self.assertEqual(result["snapshot_unavailable"], "RuntimeError")

    def _run_fixture(self, outcomes):
        steps = validate_steps([{"action": "reload", "expect_text": [f"state-{i}"]} for i in range(3)])
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch("factory26_harness.browser_probe._npm_install", return_value=(0, "", 0)))
            stack.enter_context(patch("factory26_harness.browser_probe.subprocess.Popen"))
            stack.enter_context(patch("factory26_harness.browser_probe._wait_for_health", return_value=(True, "ready")))
            stop = stack.enter_context(patch("factory26_harness.browser_probe._stop_server"))
            package = types.ModuleType("playwright")
            api = types.ModuleType("playwright.sync_api")
            api.sync_playwright = runtime = MagicMock()
            package.sync_api = api
            stack.enter_context(patch.dict(sys.modules, {"playwright": package, "playwright.sync_api": api}))
            browser = runtime.return_value.__enter__.return_value.chromium.launch.return_value
            stack.enter_context(patch("factory26_harness.browser_probe._settled_observation", return_value=scene()))
            run_step = stack.enter_context(patch("factory26_harness.browser_probe._observe_probe_step", side_effect=outcomes))
            result = _probe_isolated_app(Path("/fixture"), 3917, steps)
            count = run_step.call_count
            browser.close.assert_called_once()
            browser.new_context.return_value.close.assert_called_once()
            stop.assert_called_once()
        return result, count

    def test_failed_step_stops_flow_preserves_prior_observation_and_never_passes(self):
        failed = {**scene("Wrong form"), "execution_error": {"type": "TimeoutError", "message": "missing label"},
                  "observation_only": True}
        result, calls = self._run_fixture([scene("state-0"), failed, scene("not executed")])
        self.assertEqual(calls, 2)
        self.assertFalse(result["ok"])
        self.assertEqual(result["execution_error"]["step"], 2)
        self.assertEqual(result["behavioral_checks"], 1)
        self.assertEqual(result["attempted_behavioral_checks"], 2)
        self.assertEqual(result["behavioral_assertions"], 1)
        self.assertEqual([x["visible_text"] for x in result["observations"]],
                         ["Create record", "state-0", "Wrong form"])

    def test_success_path_keeps_all_checks_and_counts(self):
        result, calls = self._run_fixture([scene(f"state-{i}") for i in range(3)])
        self.assertTrue(result["ok"])
        self.assertIsNone(result["execution_error"])
        self.assertEqual((calls, result["behavioral_checks"], result["behavioral_assertions"]), (3, 3, 3))

    def test_failure_scene_survives_tool_compaction_and_keeps_verification_blocked(self):
        failed_scene = {**scene("form text " * 280), "observation_only": True}
        failed_result = {"ok": False, "workspace_isolated": True, "behavioral_checks": 1,
                         "behavioral_assertions": 1, "execution_error": {
                             "step": 2, "type": "TimeoutError", "message": "missing label"},
                         "observations": [scene("history " * 1000)] * 5 + [failed_scene]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = ProductionTrace(root / "trace.jsonl")
            tools = WorkspaceTools(root, trace, 3917)
            tools.last_validation_passed = True
            tools.validated_revision = 0
            tools.validation_scope = "quick"
            steps = [{"action": "reload", "expect_text": ["Saved"]}]
            with patch("factory26_harness.workspace_tools.probe_local_app", return_value=failed_result):
                encoded = tools.execute("browser_probe", {"steps": steps})
            result = json.loads(encoded)
            self.assertLessEqual(len(encoded), MAX_TOOL_RESULT_CHARS)
            self.assertTrue(result["truncated"])
            self.assertEqual(result["execution_error"], failed_result["execution_error"])
            self.assertTrue(result["observations"][0]["observation_only"])
            self.assertEqual(result["observations"][0]["controls"][0]["name"], "Record name")
            self.assertFalse(result["ok"])
            self.assertTrue(tools.browser_probe_requires_recheck)
            self.assertEqual(tools.browser_probe_calls, 1)
            self.assertEqual(tools.verified_browser_steps, [])
            rows = [json.loads(x) for x in trace.path.read_text().splitlines()]
            self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])


if __name__ == "__main__":
    unittest.main()
