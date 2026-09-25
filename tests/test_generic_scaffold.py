from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from factory26_harness.generic_scaffold import scaffold_workspace
from factory26_harness.agent import SYSTEM_PROMPT


class GenericScaffoldTests(unittest.TestCase):
    def test_transaction_response_cannot_replace_the_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold_workspace(root)
            script = """import {loadState, saveState, updateState, transactState} from './storage.mjs';
const seed = {items: ['existing'], counters: {writes: 0}};
// Reproduce the old contract mismatch with neutral data, not a task solution.
await saveState(seed);
await updateState(state => { state.items.push('lost'); return {receipt: 'old'}; });
const wrongContract = await loadState();
await saveState(seed);
const result = await transactState(draft => {
  draft.items.push('kept');
  draft.counters.writes += 1;
  return {receipt: 'new'};
});
result.receipt = 'caller-only';
const persisted = await loadState();
const files = await (await import('node:fs/promises')).readdir('./data');
console.log(JSON.stringify({wrongContract, result, persisted, files}));
"""
            run = subprocess.run(
                ["node", "--input-type=module", "-e", script], cwd=root / "backend",
                capture_output=True, text=True, check=False, timeout=20,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(run.stdout)
            self.assertEqual(result["wrongContract"], {"receipt": "old"})
            self.assertEqual(result["result"], {"receipt": "caller-only"})
            self.assertEqual(result["persisted"], {
                "items": ["existing", "kept"], "counters": {"writes": 1},
            })
            self.assertEqual(result["files"], ["state.json"])
            restarted = subprocess.run(
                ["node", "--input-type=module", "-e",
                 "import {loadState} from './storage.mjs'; console.log(JSON.stringify(await loadState()));"],
                cwd=root / "backend", capture_output=True, text=True, check=True, timeout=20,
            )
            self.assertEqual(json.loads(restarted.stdout), result["persisted"])

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
            self.assertIn("mutable-state invariants INSIDE updater", helper)
            self.assertIn("invariants INSIDE its fresh draft", SYSTEM_PROMPT)
            self.assertIn("REPLACES THE WHOLE DATABASE", SYSTEM_PROMPT)

    def test_transaction_queue_atomic_rejection_and_legacy_interoperation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold_workspace(root)
            script = """import {loadState, saveState, updateState, transactState} from './storage.mjs';
await saveState({items: [], count: 0});
const replies = await Promise.allSettled(Array.from({length: 8}, () => transactState(async draft => {
  if (draft.items.includes('one-slot')) throw new Error('duplicate');
  await new Promise(resolve => setTimeout(resolve, 2));
  draft.items.push('one-slot');
  return {receipt: 'ok'};
})));
await transactState(draft => { draft.leaked = true; throw new Error('reject'); }).catch(() => {});
await transactState(draft => { draft.nonJson = 1n; }).catch(() => {});
const afterRejections = await loadState();
const order = await Promise.all([
  transactState(async draft => {
    await new Promise(resolve => setTimeout(resolve, 2));
    draft.count += 1; return draft.count;
  }),
  updateState(draft => ({...draft, count: draft.count + 1})),
  transactState(draft => { draft.count += 1; return draft.count; }),
]);
const noResult = await transactState(draft => { draft.recovered = true; });
console.log(JSON.stringify({accepted: replies.filter(r => r.status === 'fulfilled').length,
  rejected: replies.filter(r => r.status === 'rejected').length,
  receipt: replies.find(r => r.status === 'fulfilled').value,
  afterRejections, order, undefinedResult: noResult === undefined, final: await loadState()}));
"""
            run = subprocess.run(
                ["node", "--input-type=module", "-e", script], cwd=root / "backend",
                capture_output=True, text=True, check=False, timeout=20,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(run.stdout)
            self.assertEqual((result["accepted"], result["rejected"]), (1, 7))
            self.assertEqual(result["receipt"], {"receipt": "ok"})
            self.assertEqual(result["afterRejections"], {"items": ["one-slot"], "count": 0})
            self.assertEqual(result["order"], [1, {"items": ["one-slot"], "count": 2}, 3])
            self.assertTrue(result["undefinedResult"])
            self.assertEqual(result["final"], {"items": ["one-slot"], "count": 3, "recovered": True})

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
