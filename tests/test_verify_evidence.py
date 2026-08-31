from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from factory26_harness.evidence import _export_trace
from factory26_harness.trace import ProductionTrace, reseal_trace_rows
from factory26_harness.verify_evidence import (
    _verify_sanitized_transformation,
    verify_evidence_bundle,
)


class EvidenceVerifierTests(unittest.TestCase):
    def test_recomputes_the_declared_sanitized_trace_transformation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exact = root / "exact.jsonl"
            sanitized = root / "sanitized.jsonl"
            project = root / "generated"
            repository = root / "repository"
            trace = ProductionTrace(exact)
            trace.record(
                "run_started",
                output_dir=str(project),
                requirement_path=str(
                    repository / ".cache/public-tasks/github/requirements"
                ),
            )
            trace.record("build_completed", output=str(project / "frontend"))
            metadata = _export_trace(
                exact,
                sanitized,
                (
                    (str(project), "<github-generated-project>"),
                    (str(repository), "<harness-repository>"),
                ),
            )
            exact_rows = [
                json.loads(line) for line in exact.read_text().splitlines()
            ]
            sanitized_rows = [
                json.loads(line) for line in sanitized.read_text().splitlines()
            ]
            _verify_sanitized_transformation(
                domain="github",
                exact_rows=exact_rows,
                sanitized_rows=sanitized_rows,
                trace_export=metadata,
            )

            sanitized_rows[1]["payload"]["output"] = "fabricated"
            with self.assertRaisesRegex(ValueError, "not the declared exact"):
                _verify_sanitized_transformation(
                    domain="github",
                    exact_rows=exact_rows,
                    sanitized_rows=reseal_trace_rows(sanitized_rows),
                    trace_export=metadata,
                )

    def test_rejects_manifest_path_escape_before_reading_external_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "version": 2,
                        "files": [
                            {
                                "path": "../outside.json",
                                "sha256": "0" * 64,
                                "bytes": 0,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unsafe evidence path"):
                verify_evidence_bundle(root)

    def test_rejects_changed_file_named_by_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "artifact.json"
            target.write_text("{}", encoding="utf-8")
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "version": 2,
                        "files": [
                            {
                                "path": "artifact.json",
                                "sha256": digest,
                                "bytes": target.stat().st_size,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            target.write_text('{"changed":true}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash or size mismatch"):
                verify_evidence_bundle(root)


if __name__ == "__main__":
    unittest.main()
