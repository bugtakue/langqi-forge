from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from factory26_harness.feedback import parse_playwright_json, repair_packets
from factory26_harness.impact import ChangeImpactGraph


class FeedbackTests(unittest.TestCase):
    def test_same_locator_failures_form_one_repair_packet(self) -> None:
        payload = {
            "suites": [
                {
                    "file": "tests/REQ-2.2.spec.ts",
                    "specs": [
                        {
                            "id": "REQ-2.2-a",
                            "title": "REQ-2.2 create note",
                            "tests": [
                                {
                                    "results": [
                                        {
                                            "status": "failed",
                                            "errors": [{"message": "Error: element not found\nLocator: getByRole('button', { name: /save/i })"}],
                                        }
                                    ]
                                }
                            ],
                        },
                        {
                            "id": "REQ-2.2-b",
                            "title": "REQ-2.2 save note",
                            "tests": [
                                {
                                    "results": [
                                        {
                                            "status": "timedOut",
                                            "errors": [{"message": "Timeout 10000ms\nwaiting for getByRole('button', { name: /save/i })"}],
                                        }
                                    ]
                                }
                            ],
                        },
                    ],
                }
            ]
        }
        failures = parse_playwright_json(payload)
        with tempfile.TemporaryDirectory() as directory:
            impact = ChangeImpactGraph(Path(directory) / "impact.json")
            impact.record_requirement_files(["REQ-2.2"], ["frontend/src/app.js"])
            packets = repair_packets(failures, impact)
        self.assertEqual(len(failures), 2)
        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0]["failure_count"], 2)
        self.assertEqual(packets[0]["related_files"], ["frontend/src/app.js"])


if __name__ == "__main__":
    unittest.main()
