from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory26_harness.checks import (
    javascript_scope_check, javascript_syntax_check, run_quick_checks,
)
from factory26_harness.generic_scaffold import scaffold_workspace


class JavaScriptScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        scaffold_workspace(self.root)
        self.app = self.root / "frontend/src/app.js"

    def test_scaffold_passes_with_browser_and_node_globals(self) -> None:
        result = javascript_scope_check(self.root)
        self.assertTrue(result.passed, result.summary)

    def test_catch_branch_undefined_names_fail_before_build(self) -> None:
        self.app.write_text('''async function submit() {
          try { await Promise.reject(new Error("invalid")); }
          catch (err) { passwordInput.value = ""; confirmInput.value = ""; }
        }
        document.querySelector("button")?.addEventListener("click", submit);
        ''', encoding="utf-8")
        self.assertTrue(javascript_syntax_check(self.root).passed)
        result = javascript_scope_check(self.root)
        self.assertFalse(result.passed)
        self.assertIn("passwordInput", result.summary)
        self.assertIn("confirmInput", result.summary)
        self.assertIn("frontend/src/app.js:3:", result.summary)
        checks = run_quick_checks(self.root)
        self.assertEqual(checks[-1].name, "javascript_scope")
        self.assertFalse(checks[-1].passed)

    def test_lexical_binding_destructuring_imports_and_properties_pass(self) -> None:
        self.app.write_text('''import {thing as renamed} from "./not-executed.js";
        function render({value: input}, ...rest) {
          const obj = {passwordInput: input};
          try { throw new Error("fixture"); } catch (error) { console.log(error); }
          class Box { #value; constructor(value) { this.#value = value; }
            get() { return this.#value; } }
          return [obj.passwordInput, renamed, rest.map(x => new Box(x))];
        }
        document.body.textContent = JSON.stringify(render({value: 1}));
        ''', encoding="utf-8")
        result = javascript_scope_check(self.root)
        self.assertTrue(result.passed, result.summary)

    def test_browser_names_not_node_names_and_typeof_is_safe(self) -> None:
        self.app.write_text('''const available = typeof notInstalled === "object";
        window.setTimeout(() => localStorage.setItem("test", String(available)), 0);
        document.title = "scope";
        ''', encoding="utf-8")
        self.assertTrue(javascript_scope_check(self.root).passed)
        self.app.write_text("console.log(process.env.PATH);", encoding="utf-8")
        self.assertFalse(javascript_scope_check(self.root).passed)
        self.app.write_text("console.log(typeof notInstalled.child);", encoding="utf-8")
        self.assertFalse(javascript_scope_check(self.root).passed)

    def test_commonjs_and_esm_globals_are_distinct(self) -> None:
        common = self.root / "backend/example.cjs"
        common.write_text("module.exports = require('node:path').join(__dirname, 'a');",
                          encoding="utf-8")
        self.assertTrue(javascript_scope_check(self.root).passed)
        (self.root / "backend/example.mjs").write_text("console.log(__dirname);",
                                                        encoding="utf-8")
        result = javascript_scope_check(self.root)
        self.assertFalse(result.passed)
        self.assertIn("backend/example.mjs", result.summary)
        self.assertNotIn("backend/example.cjs", result.summary)

    def test_nearest_package_type_controls_js(self) -> None:
        directory = self.root / "backend/nested"
        directory.mkdir()
        package = directory / "package.json"
        package.write_text('{"type":"commonjs"}', encoding="utf-8")
        (directory / "a.js").write_text("module.exports = __dirname;", encoding="utf-8")
        self.assertTrue(javascript_scope_check(self.root).passed)
        package.write_text('{"type":"module"}', encoding="utf-8")
        self.assertFalse(javascript_scope_check(self.root).passed)
        package.write_text('null', encoding="utf-8")
        self.assertFalse(javascript_scope_check(self.root).passed)

    def test_bundled_checker_runs_without_node_modules_and_is_portable(self) -> None:
        source = Path(__file__).resolve().parents[1] / "factory26_harness/vendor/javascript_scope.cjs"
        destination = self.root / "offline-check.cjs"
        shutil.copyfile(source, destination)
        payload = {"files": [{"path": "frontend/src/example.js", "source":
            "document.title = wrongName;", "environment": "browser", "sourceType": "module"}]}
        result = subprocess.run(
            ["node", str(destination)], input=json.dumps(payload), text=True,
            capture_output=True, cwd=self.root, timeout=15, check=True,
            env={"PATH": os.environ["PATH"]},
        )
        self.assertIn("wrongName", result.stdout)
        self.assertFalse((self.root / "node_modules").exists())

    def test_source_config_inline_comments_and_env_cannot_disable_or_execute(self) -> None:
        sentinel = self.root / "unexpected-execution"
        self.app.write_text('''/* eslint-disable no-undef */ /* global hiddenName */
        // Comments and strings are not executable identifier references.
        const text = "missingStringName";
        hiddenName.value = text;
        ''', encoding="utf-8")
        (self.root / "eslint.config.mjs").write_text(
            f'import fs from "node:fs"; fs.writeFileSync({json.dumps(str(sentinel))}, "bad");',
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"NODE_OPTIONS": "--invalid-for-scope-check"}):
            result = javascript_scope_check(self.root)
        self.assertFalse(result.passed)
        self.assertIn("hiddenName", result.summary)
        self.assertNotIn("missingStringName", result.summary)
        self.assertFalse(sentinel.exists())
        (self.root / "backend/not-run.mjs").write_text(
            f'import fs from "node:fs"; fs.writeFileSync({json.dumps(str(sentinel))}, "bad");',
            encoding="utf-8",
        )
        self.app.write_text("document.title = 'ok';", encoding="utf-8")
        self.assertTrue(javascript_scope_check(self.root).passed)
        self.assertFalse(sentinel.exists())

    def test_symlink_and_oversize_sources_fail_closed(self) -> None:
        linked = self.root / "frontend/src/linked.js"
        linked.symlink_to(self.app)
        self.assertFalse(javascript_scope_check(self.root).passed)
        linked.unlink()
        with patch("factory26_harness.checks.MAX_SCOPE_PAYLOAD_BYTES", 10):
            self.assertFalse(javascript_scope_check(self.root).passed)

    def test_parse_timeout_missing_checker_and_malformed_output_fail_closed(self) -> None:
        self.app.write_text("const a = ;", encoding="utf-8")
        self.assertFalse(javascript_scope_check(self.root).passed)
        self.app.write_text("export {};", encoding="utf-8")
        for outcome in [
            subprocess.TimeoutExpired("node", 15),
            subprocess.CompletedProcess([], 1, b"", b""),
            subprocess.CompletedProcess([], 0, b'{"results":[]}', b""),
        ]:
            with self.subTest(outcome=outcome), patch(
                "factory26_harness.checks.subprocess.run",
                **({"side_effect": outcome} if isinstance(outcome, Exception)
                   else {"return_value": outcome}),
            ):
                self.assertFalse(javascript_scope_check(self.root).passed)


if __name__ == "__main__":
    unittest.main()
