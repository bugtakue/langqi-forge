from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory26_harness.browser_probe import probe_local_app, validate_steps
from factory26_harness.checks import frontend_build_check
from factory26_harness.generic_scaffold import scaffold_workspace
from factory26_harness.trace import ProductionTrace
from factory26_harness.workspace_tools import WorkspaceTools


class BrowserProbeTests(unittest.TestCase):
    def test_steps_are_semantic_and_remote_navigation_is_rejected(self) -> None:
        for steps in (
            [{"action": "navigate", "path": "https://example.com"}],
            [{"action": "navigate", "path": "//example.com"}],
            [{"action": "navigate", "path": "/safe#fragment"}],
            [{"action": "click", "text": "Save", "role": "button", "name": "Save"}],
            [{"action": "fill", "text": "Name", "value": "Alice"}],
            [{"action": "click", "role": "button"}],
            [{"action": "evaluate", "value": "document.body.innerText"}],
            [{"action": "reload"}] * 9,
        ):
            with self.subTest(steps=steps), self.assertRaises(ValueError):
                validate_steps(steps)

        valid = validate_steps(
            [
                {"action": "fill", "label": "Name", "value": "Alice"},
                {
                    "action": "click",
                    "role": "button",
                    "name": "Save",
                    "expect_text": ["Saved: Alice"],
                },
                {"action": "reload", "expect_text": ["Saved: Alice"]},
            ]
        )
        self.assertEqual(len(valid), 3)
        self.assertEqual(valid[1]["expect_text"], ["Saved: Alice"])

    def test_probe_requires_current_validation_and_behavioral_recheck_after_edit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = WorkspaceTools(root, ProductionTrace(root / ".arc" / "trace.jsonl"), 3917)
            steps = [
                {"action": "click", "role": "button", "name": "Save", "expect_text": ["Saved"]}
            ]
            denied = json.loads(tools.execute("browser_probe", {"steps": steps}))
            self.assertFalse(denied["ok"])
            self.assertEqual(tools.browser_probe_calls, 0)

            tools.last_validation_passed = True
            tools.validated_revision = 0
            tools.validation_scope = "quick"
            with patch(
                "factory26_harness.workspace_tools.probe_local_app",
                side_effect=[
                    {"ok": True, "behavioral_checks": 0, "behavioral_assertions": 0},
                    {"ok": True, "behavioral_checks": 1, "behavioral_assertions": 1},
                    {"ok": False, "behavioral_checks": 1, "behavioral_assertions": 1},
                ],
            ):
                inspection = json.loads(tools.execute("browser_probe", {"steps": []}))
                self.assertTrue(inspection["ok"])
                self.assertTrue(tools.browser_probe_requires_recheck)

                verified = json.loads(tools.execute("browser_probe", {"steps": steps}))
                self.assertTrue(verified["ok"])
                self.assertFalse(tools.browser_probe_requires_recheck)

                target = root / "frontend" / "src" / "app.js"
                target.parent.mkdir(parents=True)
                written = json.loads(
                    tools.execute("write_file", {"path": "frontend/src/app.js", "content": "// changed\n"})
                )
                self.assertTrue(written["ok"])
                self.assertTrue(tools.browser_probe_requires_recheck)

                tools.last_validation_passed = True
                tools.validated_revision = tools.change_revision
                tools.validation_scope = "quick"
                failed = json.loads(tools.execute("browser_probe", {"steps": steps}))
                self.assertFalse(failed["ok"])
                self.assertTrue(tools.browser_probe_requires_recheck)
                self.assertEqual(tools.browser_probe_calls, 3)
                exhausted = json.loads(tools.execute("browser_probe", {"steps": steps}))
                self.assertFalse(exhausted["ok"])
                self.assertIn("budget", exhausted["error"])

    @unittest.skipUnless(
        os.environ.get("FACTORY26_RUN_BROWSER_INTEGRATION") == "1",
        "requires a Runner image with Python Playwright and Chromium",
    )
    def test_local_chromium_exercises_a_real_click_and_blocks_external_http(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold_workspace(root)
            (root / "frontend" / "src" / "app.js").write_text(
                '''document.querySelector("#app").innerHTML =
  '<label for="name">Name</label><input id="name">'
  + '<button>Save</button><p id="status"></p>';
document.querySelector("button").addEventListener("click", () => {
  document.querySelector("#status").textContent =
    "Saved: " + document.querySelector("#name").value;
});
fetch("https://example.com/blocked").catch(() => {});
''',
                encoding="utf-8",
            )
            built = frontend_build_check(root)
            self.assertTrue(built.passed, built.summary)
            result = probe_local_app(
                root,
                19118,
                [
                    {"action": "fill", "label": "Name", "value": "Alice"},
                    {
                        "action": "click",
                        "role": "button",
                        "name": "Save",
                        "expect_text": ["Saved: Alice"],
                    },
                    {"action": "reload", "expect_absent": ["Saved: Alice"]},
                ],
            )
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["behavioral_assertions"], 2)
            self.assertIn("example.com", result["blocked_external_hosts"])


if __name__ == "__main__":
    unittest.main()
