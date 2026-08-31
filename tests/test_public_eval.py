from __future__ import annotations

import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from factory26_harness.public_eval import (
    _backend_environment,
    _evaluation_environment,
    _playwright_runtime_contract,
    _reserve_run_label,
    _write,
)
from factory26_harness.public_fixtures import public_fixture_environment


class PublicEvalTests(unittest.TestCase):
    def test_unpinned_playwright_runtime_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "node_modules" / "@playwright" / "test"
            package.mkdir(parents=True)
            (package / "package.json").write_text(
                '{"version":"1.62.1"}', encoding="utf-8"
            )
            (package / "cli.js").write_text(
                "console.log('forged green report')\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "CLI hash"):
                _playwright_runtime_contract(root)

    def test_evaluator_environment_drops_host_secrets_and_forces_fixtures(self) -> None:
        hostile = {
            "PATH": os.environ.get("PATH", "/usr/bin"),
            "OPENAI_API_KEY": "must-not-reach-generated-code",
            "DASHSCOPE_API_KEY": "must-not-reach-generated-code",
            "NODE_OPTIONS": "--require=/tmp/forge-report.js",
            "E2E_LOGIN_USERNAME": "host-controlled-user",
            "FACTORY26_RESET_FIXTURES": "0",
        }
        with patch.dict(os.environ, hostile, clear=True):
            environment = _evaluation_environment(
                E2E_BASE_URL="http://127.0.0.1:3900"
            )
            environment.update(
                public_fixture_environment(
                    "github", environment["E2E_BASE_URL"], "baseline"
                )
            )
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("DASHSCOPE_API_KEY", environment)
        self.assertNotIn("NODE_OPTIONS", environment)
        self.assertEqual(environment["E2E_LOGIN_USERNAME"], "fixture-user-01")
        self.assertEqual(environment["FACTORY26_RESET_FIXTURES"], "1")

        backend = _backend_environment(
            3900,
            public_fixture_environment(
                "github", "http://127.0.0.1:3900", "baseline"
            ),
        )
        self.assertNotIn("FACTORY26_PUBLIC_TEST_DIR", backend)
        self.assertNotIn("FACTORY26_PUBLIC_WORKERS", backend)
        self.assertNotIn("E2E_BASE_URL", backend)
        self.assertEqual(backend["PORT"], "3900")

    def test_atomic_writer_is_safe_for_parallel_evaluators(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "playwright.config.mjs"
            values = [f"config-{index}\n" for index in range(40)]
            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(lambda value: _write(target, value), values))
            self.assertIn(target.read_text(encoding="utf-8"), values)
            self.assertEqual(list(target.parent.glob(f".{target.name}.*.tmp")), [])

    def test_public_evaluation_labels_are_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _reserve_run_label(root, "github")
            (root / "github.feedback.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "immutable"):
                _reserve_run_label(root, "github")


if __name__ == "__main__":
    unittest.main()
