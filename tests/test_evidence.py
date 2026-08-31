from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from factory26_harness.evidence import _export_trace, _sanitize


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


if __name__ == "__main__":
    unittest.main()
