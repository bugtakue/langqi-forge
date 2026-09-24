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


if __name__ == "__main__":
    unittest.main()
