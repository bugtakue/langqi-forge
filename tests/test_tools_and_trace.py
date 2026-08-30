from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from factory26_harness.impact import ChangeImpactGraph
from factory26_harness.trace import ProductionTrace
from factory26_harness.workspace_tools import WorkspaceTools


class ToolAndTraceTests(unittest.TestCase):
    def test_writes_are_scoped_and_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = ProductionTrace(root / ".arc" / "trace.jsonl")
            tools = WorkspaceTools(root, trace, smoke_port=3911)
            ok = json.loads(tools.execute("write_file", {"path": "frontend/src/app.js", "content": "ok\n"}))
            denied = json.loads(tools.execute("write_file", {"path": "../escape.txt", "content": "bad"}))
            self.assertTrue(ok["ok"])
            self.assertFalse(denied["ok"])
            self.assertEqual(tools.changed_files, {"frontend/src/app.js"})

    def test_trace_redacts_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            ProductionTrace(path).record("request", api_key="secret", nested={"Authorization": "Bearer secret"})
            row = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(row["payload"]["api_key"], "[REDACTED]")
            self.assertEqual(row["payload"]["nested"]["Authorization"], "[REDACTED]")

    def test_impact_graph_uses_observed_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            graph = ChangeImpactGraph(Path(directory) / "impact.json")
            graph.record_requirement_files(["R1"], ["frontend/src/app.js"])
            graph.record_requirement_files(["R2"], ["backend/server.mjs"])
            self.assertEqual(graph.files_for_requirements(["R2", "R1"]), ["backend/server.mjs", "frontend/src/app.js"])


if __name__ == "__main__":
    unittest.main()
