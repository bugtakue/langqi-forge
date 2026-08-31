from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from factory26_harness.artifacts import (
    application_source_manifest,
    verify_run_envelope,
    write_run_envelope,
)
from factory26_harness.trace import ProductionTrace


class ArtifactEnvelopeTests(unittest.TestCase):
    def _project(self, root: Path) -> Path:
        for relative in ("frontend/src/app.js", "backend/server.mjs"):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"// {relative}\n", encoding="utf-8")
        arc = root / ".arc"
        arc.mkdir()
        run_id = "11111111-1111-4111-8111-111111111111"
        source = application_source_manifest(root)
        report = {
            "version": 2,
            "run_id": run_id,
            "requirement_sha256": "r" * 64,
            "application_source": source,
        }
        (arc / "harness-report.json").write_text(json.dumps(report), encoding="utf-8")
        (arc / "planner-contract.json").write_text(
            json.dumps({"run_id": run_id}), encoding="utf-8"
        )
        (arc / "compiled-plan.json").write_text(
            json.dumps({"run_id": run_id}), encoding="utf-8"
        )
        ProductionTrace(arc / "production-trace.jsonl").record(
            "run_completed", report=report
        )
        return root

    def test_envelope_binds_source_report_plan_and_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self._project(Path(temporary))
            written = write_run_envelope(root)
            self.assertEqual(verify_run_envelope(root), written)
            (root / "frontend" / "src" / "app.js").write_text(
                "// changed\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "application source"):
                verify_run_envelope(root)

    def test_envelope_rejects_report_not_equal_to_completed_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self._project(Path(temporary))
            report_path = root / ".arc" / "harness-report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["extra"] = "forged after completion"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "run_completed report"):
                write_run_envelope(root)


if __name__ == "__main__":
    unittest.main()
