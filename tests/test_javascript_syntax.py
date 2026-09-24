from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory26_harness.checks import (
    _run,
    frontend_build_check,
    javascript_syntax_check,
    run_full_checks,
    run_quick_checks,
    startup_check,
)
from factory26_harness.generic_scaffold import scaffold_workspace
from factory26_harness.trace import ProductionTrace
from factory26_harness.workspace_tools import WorkspaceTools


class JavaScriptSyntaxTests(unittest.TestCase):
    def test_timeout_bytes_become_a_validation_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "factory26_harness.checks.subprocess.run",
                side_effect=subprocess.TimeoutExpired(
                    ["node", "--check", "app.js"], 10,
                    output=b"partial stdout", stderr=b"partial stderr",
                ),
            ):
                code, output, _ = _run(["node", "--check", "app.js"], Path(directory), 10)
            self.assertEqual(code, 124)
            self.assertIn("partial stdout", output)
            self.assertIn("partial stderr", output)

    def test_copy_only_build_cannot_hide_frontend_parse_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold_workspace(root)
            (root / "frontend/src/app.js").write_text("const broken = ;\n", encoding="utf-8")

            self.assertTrue(frontend_build_check(root).passed)
            syntax = javascript_syntax_check(root)
            self.assertFalse(syntax.passed)
            self.assertIn("frontend/src/app.js", syntax.summary)
            quick = run_quick_checks(root)
            self.assertEqual(quick[-1].name, "javascript_syntax")
            self.assertFalse(quick[-1].passed)
            full = run_full_checks(root, 3925)
            self.assertEqual(full[-1].name, "javascript_syntax")
            self.assertFalse(full[-1].passed)

            tools = WorkspaceTools(root, ProductionTrace(root / ".arc/trace.jsonl"), 3925)
            result = json.loads(tools.execute("run_validation", {"scope": "quick"}))
            self.assertFalse(result["ok"])
            self.assertFalse(result["current_changes_validated"])

    def test_backend_parse_error_is_caught_without_executing_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold_workspace(root)
            server = root / "backend/server.mjs"
            server.write_text("const broken = ;\n", encoding="utf-8")
            result = javascript_syntax_check(root)
            self.assertFalse(result.passed)
            self.assertIn("backend/server.mjs", result.summary)

            server.write_text("process.exit(55);\n", encoding="utf-8")
            repaired = javascript_syntax_check(root)
            self.assertTrue(repaired.passed, repaired.summary)

    def test_noop_build_cannot_pass_with_stale_dist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold_workspace(root)
            self.assertTrue(frontend_build_check(root).passed)
            package_path = root / "frontend/package.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["scripts"]["build"] = 'node -e ""'
            package_path.write_text(json.dumps(package), encoding="utf-8")
            result = frontend_build_check(root)
            self.assertFalse(result.passed)
            self.assertIn("dist/index.html", result.summary)
            self.assertFalse((root / "frontend/dist/index.html").exists())

    def test_startup_health_check_does_not_modify_original_seed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold_workspace(root)
            state_path = root / "backend/data/state.json"
            state_path.write_text('{"count":0}\n', encoding="utf-8")
            server_path = root / "backend/server.mjs"
            source = server_path.read_text(encoding="utf-8")
            source = source.replace(
                'import { readFile } from "node:fs/promises";',
                'import { readFile, writeFile } from "node:fs/promises";',
                1,
            )
            source = source.replace(
                'const here = path.dirname(fileURLToPath(import.meta.url));',
                '''const here = path.dirname(fileURLToPath(import.meta.url));
const statePath = path.join(here, "data", "state.json");
const state = JSON.parse(await readFile(statePath, "utf8"));
await writeFile(statePath, JSON.stringify({ ...state, count: state.count + 1 }));''',
                1,
            )
            server_path.write_text(source, encoding="utf-8")
            self.assertTrue(frontend_build_check(root).passed)
            result = startup_check(root, 3926)
            self.assertTrue(result.passed, result.summary)
            self.assertEqual(
                json.loads(state_path.read_text(encoding="utf-8")), {"count": 0}
            )

    def test_frontend_build_check_rejects_seed_mutating_script(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold_workspace(root)
            state_path = root / "backend/data/state.json"
            state_path.write_text('{"count":0}\n', encoding="utf-8")
            build_path = root / "frontend/build.mjs"
            build_path.write_text(
                build_path.read_text(encoding="utf-8")
                + '''\nimport { readFile, writeFile } from "node:fs/promises";
const statePath = path.resolve("../backend/data/state.json");
const state = JSON.parse(await readFile(statePath, "utf8"));
await writeFile(statePath, JSON.stringify({ ...state, count: state.count + 1 }));
''',
                encoding="utf-8",
            )
            result = frontend_build_check(root)
            self.assertFalse(result.passed)
            self.assertIn("outside dist", result.summary)
            self.assertFalse((root / "frontend/dist/index.html").exists())
            self.assertEqual(
                json.loads(state_path.read_text(encoding="utf-8")), {"count": 0}
            )

    def test_frontend_build_rejects_linked_output_before_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold_workspace(root)
            build_path = root / "frontend/build.mjs"
            build_path.write_text(
                build_path.read_text(encoding="utf-8")
                + '''\nimport { symlink } from "node:fs/promises";
await symlink("../src/app.js", path.resolve("dist/linked.js"));
''',
                encoding="utf-8",
            )
            result = frontend_build_check(root)
            self.assertFalse(result.passed)
            self.assertIn("unsafe", result.summary)
            self.assertFalse((root / "frontend/dist/index.html").exists())

    def test_frontend_build_rejects_source_rewrite_outside_dist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold_workspace(root)
            app_path = root / "frontend/src/app.js"
            original_app = app_path.read_text(encoding="utf-8")
            build_path = root / "frontend/build.mjs"
            build_path.write_text(
                build_path.read_text(encoding="utf-8")
                + '''\nimport { writeFile } from "node:fs/promises";
await writeFile(path.resolve("src/app.js"), "// rewritten by build\\n");
''',
                encoding="utf-8",
            )
            result = frontend_build_check(root)
            self.assertFalse(result.passed)
            self.assertIn("frontend/src/app.js", result.summary)
            self.assertFalse((root / "frontend/dist/index.html").exists())
            self.assertEqual(app_path.read_text(encoding="utf-8"), original_app)

    def test_frontend_build_rejects_new_file_outside_dist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold_workspace(root)
            build_path = root / "frontend/build.mjs"
            build_path.write_text(
                build_path.read_text(encoding="utf-8")
                + '''\nimport { writeFile } from "node:fs/promises";
await writeFile(path.resolve("../backend/generated.json"), "{}\\n");
''',
                encoding="utf-8",
            )
            result = frontend_build_check(root)
            self.assertFalse(result.passed)
            self.assertIn("backend/generated.json", result.summary)
            self.assertFalse((root / "frontend/dist/index.html").exists())
            self.assertFalse((root / "backend/generated.json").exists())


if __name__ == "__main__":
    unittest.main()
