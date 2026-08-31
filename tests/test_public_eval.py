from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from factory26_harness.public_eval import _write, ensure_playwright


class PublicEvalTests(unittest.TestCase):
    def test_existing_playwright_runtime_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "node_modules" / ".bin" / "playwright"
            binary.parent.mkdir(parents=True)
            binary.write_text("#!/bin/sh\n", encoding="utf-8")
            resolved = ensure_playwright(root)
            self.assertEqual(resolved, binary)
            self.assertTrue((root / "package.json").is_file())
            self.assertTrue((root / "playwright.config.mjs").is_file())

    def test_atomic_writer_is_safe_for_parallel_evaluators(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "playwright.config.mjs"
            values = [f"config-{index}\n" for index in range(40)]
            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(lambda value: _write(target, value), values))
            self.assertIn(target.read_text(encoding="utf-8"), values)
            self.assertEqual(list(target.parent.glob(f".{target.name}.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
