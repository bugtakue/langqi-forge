import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from factory26_harness import trace as trace_module
from factory26_harness.trace import EVIDENCE_ARCHIVE_NAME, ProductionTrace, verify_trace_rows


class EvidenceExportTests(unittest.TestCase):
    def make_trace(self, root):
        trace = ProductionTrace(root / ".arc/production-trace.jsonl")
        trace.record("model_request", messages=[{"role": "user", "content": "Build a notes app"}],
                     api_key="private-do-not-export")
        trace.record("tool_call", tool="write_file", arguments={"path": "frontend/src/app.js"})
        trace.record("human_intervention_checkpoint", intervention_count=0)
        trace.record("run_failed", error="fixture generation failure")
        return trace

    def test_exports_exact_sealed_trace_and_redacted_report_with_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = self.make_trace(root)
            report = {"run_id": "fixture", "status": "failed", "password": "report-secret",
                      "behavioral_gui_tested": False, "source": {"revision": "a" * 40}}
            receipt = trace.export_evidence(report)
            target = root / EVIDENCE_ARCHIVE_NAME
            self.assertEqual(receipt["sha256"], hashlib.sha256(target.read_bytes()).hexdigest())
            self.assertEqual(receipt["bytes"], target.stat().st_size)
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(set(archive.namelist()), {
                    "production-trace.jsonl", "harness-report.json", "evidence-manifest.json"})
                raw = archive.read("production-trace.jsonl")
                self.assertEqual(raw, trace.path.read_bytes())
                self.assertNotIn(b"private-do-not-export", raw)
                rows = [json.loads(line) for line in raw.splitlines()]
                self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])
                exported_report = archive.read("harness-report.json")
                self.assertNotIn(b"report-secret", exported_report)
                self.assertEqual(json.loads(exported_report)["status"], "failed")
                manifest = json.loads(archive.read("evidence-manifest.json"))
                self.assertEqual(manifest["trace"]["sha256"], hashlib.sha256(raw).hexdigest())
                self.assertEqual(manifest["report_sha256"], hashlib.sha256(exported_report).hexdigest())
                self.assertFalse(manifest["independent_gui_evaluation_included"])
            self.assertEqual(report["password"], "report-secret")
            self.assertFalse((root / "frontend").exists())

    def test_rejects_tampered_trace_without_an_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = self.make_trace(root)
            trace.path.write_text(trace.path.read_text().replace("notes app", "other app"))
            with self.assertRaisesRegex(RuntimeError, "integrity"):
                trace.export_evidence({"status": "failed"})
            self.assertFalse((root / EVIDENCE_ARCHIVE_NAME).exists())

    def test_does_not_follow_or_replace_existing_archive_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = self.make_trace(root)
            sentinel = root / "keep.txt"
            sentinel.write_text("keep")
            (root / EVIDENCE_ARCHIVE_NAME).symlink_to(sentinel)
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                trace.export_evidence({})
            self.assertEqual(sentinel.read_text(), "keep")

    def test_bounded_export_rejects_oversized_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = self.make_trace(root)
            with patch("factory26_harness.trace.MAX_EXPORT_TRACE_BYTES", 10):
                with self.assertRaisesRegex(RuntimeError, "limits"):
                    trace.export_evidence({})
            self.assertFalse((root / EVIDENCE_ARCHIVE_NAME).exists())

    def test_copy_failure_does_not_leave_partial_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = self.make_trace(root)
            with patch.object(trace_module, "_inspect_export_trace", side_effect=OSError("fixture failure")):
                with self.assertRaises(OSError):
                    trace.export_evidence({})
            self.assertFalse((root / EVIDENCE_ARCHIVE_NAME).exists())
            self.assertFalse(list(root.glob(".factory26-evidence-*")))

    def test_rejects_valid_prefix_with_missing_terminal_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = self.make_trace(root)
            lines = trace.path.read_bytes().splitlines(keepends=True)
            trace.path.write_bytes(b"".join(lines[:-1]))
            with self.assertRaisesRegex(RuntimeError, "writer checkpoint"):
                trace.export_evidence({})
            self.assertFalse((root / EVIDENCE_ARCHIVE_NAME).exists())

    def test_copy_is_exact_snapshot_even_if_another_writer_appends_after_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = self.make_trace(root)
            original = trace.path.read_bytes()
            inspect = trace_module._inspect_export_trace

            def append_after_copy(path, destination):
                metadata = inspect(path, destination)
                ProductionTrace(path).record("late_other_writer", note="not in this writer snapshot")
                return metadata

            with patch.object(trace_module, "_inspect_export_trace", side_effect=append_after_copy):
                receipt = trace.export_evidence({})
            with zipfile.ZipFile(root / EVIDENCE_ARCHIVE_NAME) as archive:
                exported = archive.read("production-trace.jsonl")
                self.assertEqual(exported, original)
                self.assertEqual(hashlib.sha256(exported).hexdigest(), receipt["trace"]["sha256"])
            self.assertNotEqual(trace.path.read_bytes(), original)

    def test_concurrent_publication_cannot_overwrite_an_existing_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = self.make_trace(root)
            target = root / EVIDENCE_ARCHIVE_NAME
            inspect = trace_module._inspect_export_trace

            def publish_during_export(path, destination):
                metadata = inspect(path, destination)
                target.write_bytes(b"keep concurrent evidence")
                return metadata

            with patch.object(trace_module, "_inspect_export_trace", side_effect=publish_during_export):
                with self.assertRaises(FileExistsError):
                    trace.export_evidence({})
            self.assertEqual(target.read_bytes(), b"keep concurrent evidence")
            self.assertFalse(list(root.glob(".factory26-evidence-*")))
