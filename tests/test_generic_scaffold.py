from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from factory26_harness.generic_scaffold import scaffold_workspace
from factory26_harness.agent import SYSTEM_PROMPT


class GenericScaffoldTests(unittest.TestCase):
    def test_mutable_checks_must_use_the_transaction_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold_workspace(root)
            script = """import {loadState, saveState, updateState} from './storage.mjs';
await saveState({items: []});
// All callers observe the same old snapshot before their writes queue.
const oldSnapshots = await Promise.all(Array.from({length: 8}, () => loadState()));
await Promise.all(oldSnapshots.map(old => {
  if (old.items.includes('one-slot')) throw new Error('unreachable');
  return updateState(state => { state.items.push('one-slot'); return state; });
}));
const staleCheckCount = (await loadState()).items.length;
await saveState({items: []});
const replies = await Promise.allSettled(Array.from({length: 8}, () => updateState(state => {
  if (state.items.includes('one-slot')) throw new Error('duplicate');
  state.items.push('one-slot');
  return state;
})));
const checkedInside = await loadState();
// Rejected mutations must not leak into persistence, and the queue must recover.
await updateState(state => { state.leaked = true; throw new Error('rejected'); }).catch(() => {});
const afterRejection = await loadState();
await updateState(state => { state.recovered = true; return state; });
console.log(JSON.stringify({staleCheckCount, checkedInside, afterRejection,
  accepted: replies.filter(r => r.status === 'fulfilled').length,
  rejected: replies.filter(r => r.status === 'rejected').length,
  final: await loadState()}));
"""
            run = subprocess.run(
                ["node", "--input-type=module", "-e", script], cwd=root / "backend",
                capture_output=True, text=True, check=False, timeout=20,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(run.stdout)
            self.assertEqual(result["staleCheckCount"], 8)
            self.assertEqual(result["accepted"], 1)
            self.assertEqual(result["rejected"], 7)
            self.assertEqual(result["checkedInside"], {"items": ["one-slot"]})
            self.assertEqual(result["afterRejection"], result["checkedInside"])
            self.assertEqual(result["final"], {"items": ["one-slot"], "recovered": True})
            helper = (root / "backend/storage.mjs").read_text()
            self.assertIn("check mutable-state invariants INSIDE updater", helper)
            self.assertIn("INSIDE updateState against its fresh state", SYSTEM_PROMPT)

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
