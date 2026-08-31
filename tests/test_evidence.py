from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from factory26_harness.evidence import _export_trace, _sanitize, export_evidence
from factory26_harness.trace import (
    ProductionTrace,
    reseal_trace_rows,
    verify_trace_rows,
)


class EvidenceTests(unittest.TestCase):
    def test_sanitizes_nested_paths_without_changing_non_path_values(self) -> None:
        value = {
            "output": "/private/tmp/run/project",
            "nested": [
                "/workspace/harness/requirements",
                "https://example.com/tmp/path",
            ],
        }
        sanitized = _sanitize(
            value,
            (
                ("/private/tmp/run/project", "<generated-project>"),
                ("/workspace/harness", "<harness-repository>"),
            ),
        )
        self.assertEqual(sanitized["output"], "<generated-project>")
        self.assertEqual(sanitized["nested"][0], "<harness-repository>/requirements")
        self.assertEqual(sanitized["nested"][1], "https://example.com/tmp/path")

    def test_trace_export_requires_contiguous_sequences(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.jsonl"
            destination = root / "destination.jsonl"
            source.write_text(
                json.dumps({"sequence": 2, "payload": {"path": "/tmp/run"}}) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                _export_trace(source, destination, (("/tmp/run", "<run>"),))

    def test_trace_export_reseals_sanitized_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.jsonl"
            destination = root / "destination.jsonl"
            trace = ProductionTrace(source)
            trace.record("build", output="/tmp/private-run/frontend")
            trace.record("finish", passed=True)
            metadata = _export_trace(
                source,
                destination,
                (("/tmp/private-run", "<generated-project>"),),
            )
            rows = [
                json.loads(line)
                for line in destination.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(metadata["rows"], 2)
            self.assertEqual(
                metadata["transformation"],
                "deterministic-path-redaction-and-reseal-v2",
            )
            self.assertEqual(metadata["sanitized_sha256"], __import__("hashlib").sha256(destination.read_bytes()).hexdigest())
            self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])
            self.assertEqual(
                rows[0]["payload"]["output"], "<generated-project>/frontend"
            )

    def test_trace_export_rejects_resealed_unredacted_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.jsonl"
            destination = root / "destination.jsonl"
            rows = reseal_trace_rows(
                [
                    {
                        "sequence": 1,
                        "event": "forged",
                        "payload": {
                            "raw": "DATABASE_PASSWORD=hunter2",
                        },
                    }
                ]
            )
            source.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unredacted secret"):
                _export_trace(source, destination, ())

    def test_evidence_export_rejects_a_failed_qualification_before_copying(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            qualification = root / "qualification.json"
            qualification.write_text(
                json.dumps({"passed": False, "evidence": {}}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "failed qualification"):
                export_evidence(
                    root / "github",
                    root / "sheet",
                    qualification,
                    root / "export",
                )


if __name__ == "__main__":
    unittest.main()
