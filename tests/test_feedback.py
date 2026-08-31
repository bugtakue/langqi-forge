from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from factory26_harness.feedback import (
    parse_playwright_json,
    repair_packets,
    validate_playwright_report,
)
from factory26_harness.impact import ChangeImpactGraph


class FeedbackTests(unittest.TestCase):
    @staticmethod
    def _valid_report() -> tuple[dict, str]:
        inventory = [
            {
                "id": "stable-case-id",
                "title": "REQ-1 does the behavior",
                "file": "REQ-1-contract.spec.ts",
                "line": 7,
                "column": 1,
                "project_id": "chromium",
                "project_name": "chromium",
            }
        ]
        inventory_sha256 = hashlib.sha256(
            json.dumps(
                inventory,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        payload = {
            "config": {"workers": 4, "fullyParallel": True},
            "errors": [],
            "stats": {
                "expected": 1,
                "unexpected": 0,
                "skipped": 0,
                "flaky": 0,
            },
            "suites": [
                {
                    "file": "REQ-1-contract.spec.ts",
                    "specs": [
                        {
                            "id": "stable-case-id",
                            "title": "REQ-1 does the behavior",
                            "file": "REQ-1-contract.spec.ts",
                            "line": 7,
                            "column": 1,
                            "ok": True,
                            "tests": [
                                {
                                    "projectId": "chromium",
                                    "projectName": "chromium",
                                    "expectedStatus": "passed",
                                    "status": "expected",
                                    "results": [
                                        {
                                            "retry": 0,
                                            "status": "passed",
                                            "errors": [],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        return payload, inventory_sha256

    def test_report_contract_requires_enumerated_locked_inventory(self) -> None:
        payload, inventory_sha256 = self._valid_report()
        result = validate_playwright_report(
            payload,
            expected_test_files={"REQ-1-contract.spec.ts"},
            expected_test_count=1,
            expected_inventory_sha256=inventory_sha256,
            expected_workers=4,
            expected_fully_parallel=True,
        )
        self.assertEqual(result["test_count"], 1)
        self.assertEqual(result["inventory_sha256"], inventory_sha256)

    def test_stats_only_or_duplicated_report_cannot_claim_green(self) -> None:
        with self.assertRaisesRegex(ValueError, "no suites"):
            validate_playwright_report(
                {
                    "config": {"workers": 4, "fullyParallel": True},
                    "suites": [],
                    "stats": {
                        "expected": 101,
                        "unexpected": 0,
                        "skipped": 0,
                        "flaky": 0,
                    },
                },
                expected_test_files=None,
                expected_test_count=101,
                expected_inventory_sha256="0" * 64,
            )
        payload, inventory_sha256 = self._valid_report()
        payload["suites"].append(payload["suites"][0])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_playwright_report(
                payload,
                expected_test_files={"REQ-1-contract.spec.ts"},
                expected_test_count=1,
                expected_inventory_sha256=inventory_sha256,
            )

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
        self.assertEqual(packets[0]["classification"], "product_behavior")
        self.assertTrue(packets[0]["repair_allowed"])

    def test_hyphenated_requirement_id_is_not_truncated(self) -> None:
        payload = {
            "suites": [
                {
                    "file": "REQ-1-1-3-password-recovery.spec.ts",
                    "specs": [
                        {
                            "id": "case",
                            "title": "REQ-1-1-3 resets a password",
                            "tests": [
                                {
                                    "results": [
                                        {
                                            "status": "failed",
                                            "errors": [{"message": "Error: reset failed"}],
                                        }
                                    ]
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        failures = parse_playwright_json(payload)
        self.assertEqual(failures[0].requirement_id, "REQ-1-1-3")

    def test_browser_setup_failures_are_not_sent_to_the_code_repair_agent(self) -> None:
        payload = {
            "suites": [
                {
                    "file": "REQ-2-3-access.spec.ts",
                    "specs": [
                        {
                            "id": "infra",
                            "title": "REQ-2-3 access",
                            "tests": [
                                {
                                    "results": [
                                        {
                                            "status": "failed",
                                            "errors": [
                                                {
                                                    "message": "Error: browser.newContext: Test ended while setting up acceptDownloads"
                                                }
                                            ],
                                        }
                                    ]
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        failures = parse_playwright_json(payload)
        with tempfile.TemporaryDirectory() as directory:
            packets = repair_packets(
                failures, ChangeImpactGraph(Path(directory) / "impact.json")
            )
        self.assertEqual(packets[0]["classification"], "evaluator_infrastructure")
        self.assertFalse(packets[0]["repair_allowed"])


if __name__ == "__main__":
    unittest.main()
