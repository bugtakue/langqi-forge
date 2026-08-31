from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from factory26_harness.public_eval import ensure_playwright


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


if __name__ == "__main__":
    unittest.main()
