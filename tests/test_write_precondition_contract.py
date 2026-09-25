"""A required model-facing precondition must not weaken overwrite checks."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from factory26_harness.trace import ProductionTrace
from factory26_harness.workspace_tools import WorkspaceTools


class WritePreconditionContractTests(unittest.TestCase):
    def test_hash_is_required_and_precedes_large_content_in_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = WorkspaceTools(root, ProductionTrace(root / "trace.jsonl"), 3927)
            schema = next(row["function"] for row in tools.schemas()
                          if row["function"]["name"] == "write_file")
            parameters = schema["parameters"]
            self.assertEqual(parameters["required"], ["path", "expected_sha256", "content"])
            keys = list(parameters["properties"])
            self.assertLess(keys.index("expected_sha256"), keys.index("content"))
            self.assertIn('empty string', parameters["properties"]["expected_sha256"]["description"])

    def test_explicit_new_file_sentinel_cannot_overwrite_existing_or_stale_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = WorkspaceTools(root, ProductionTrace(root / "trace.jsonl"), 3927)
            relative = "frontend/src/example.js"
            target = root / relative
            created = json.loads(tools.execute("write_file", {
                "path": relative, "expected_sha256": "", "content": "original\n",
            }))
            self.assertTrue(created["ok"])
            before = (tools.change_revision, tools.write_operations, tools.bytes_written)
            for extra in ({}, {"expected_sha256": ""}, {"expected_sha256": "0" * 64}):
                rejected = json.loads(tools.execute("write_file", {
                    "path": relative, "content": "unwanted\n", **extra,
                }))
                self.assertFalse(rejected["ok"])
                self.assertEqual(target.read_text(), "original\n")
                self.assertEqual((tools.change_revision, tools.write_operations, tools.bytes_written), before)
            accepted = json.loads(tools.execute("write_file", {
                "path": relative, "expected_sha256": hashlib.sha256(b"original\n").hexdigest(),
                "content": "revised\n",
            }))
            self.assertTrue(accepted["ok"])
            self.assertEqual(target.read_text(), "revised\n")
            self.assertEqual(tools.change_revision, before[0] + 1)
