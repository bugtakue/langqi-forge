from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from factory26_harness.generic_scaffold import scaffold_workspace


class GenericScaffoldTests(unittest.TestCase):
    def test_neutral_foundation_and_serial_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            created = scaffold_workspace(root)
            self.assertIn("frontend/package.json", created)
            self.assertIn("backend/storage.mjs", created)
            self.assertEqual(scaffold_workspace(root), [])
            self.assertEqual((root / "backend/data/state.json").read_text(), "{}\n")
            script = """import { loadState, updateState } from './storage.mjs';
await Promise.all(Array.from({length: 20}, () => updateState(state => ({
  count: (state.count || 0) + 1,
}))));
console.log(JSON.stringify(await loadState()));
"""
            run = subprocess.run(
                ["node", "--input-type=module", "-e", script],
                cwd=root / "backend",
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout), {"count": 20})
            self.assertEqual(
                json.loads((root / "backend/data/state.json").read_text()),
                {"count": 20},
            )


if __name__ == "__main__":
    unittest.main()
