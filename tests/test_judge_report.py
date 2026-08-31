from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory26_harness.judge_report import (
    _qualification_summary,
    _safe_output,
    render_report,
)


def _domain(name: str) -> dict:
    return {
        "domain": name,
        "run_id": "run-1234567890",
        "source_revision": "revision-1234567890",
        "source_clean": True,
        "dry_run": False,
        "route": "planner-approved-deterministic-kernel",
        "planner_status": "completed",
        "requirements": 10,
        "duration_seconds": 1.5,
        "planner_iterations": 1,
        "coding_iterations": 0,
        "manual_interventions": 0,
        "local_checks_green": True,
        "model": "qwen-plus",
        "gateway": "alibaba-cloud-bailian",
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "http_attempts": 1,
        "capabilities": ["safe", "<script>alert(1)</script>"],
        "uncovered": [],
        "risks": ["permissions"],
        "validation_focus": ["persistence"],
        "evaluations": [
            {
                "label": name,
                "profile": "baseline",
                "expected": 10,
                "passed": 10,
                "unexpected": 0,
                "skipped": 0,
                "flaky": 0,
                "workers": 4,
                "duration_seconds": 2.5,
                "green": True,
                "raw_report_sha256": "a" * 64,
            }
        ],
        "capsule": {
            "id": "b" * 64,
            "profiles": ["baseline"],
            "skips_revalidation": False,
        },
        "trace": {
            "rows": 20,
            "head": "c" * 64,
            "important_events": {"model_request": 1, "run_completed": 1},
        },
        "claim_boundary": "bounded",
    }


class JudgeReportTests(unittest.TestCase):
    def test_render_is_self_contained_and_escapes_artifact_text(self) -> None:
        data = {
            "title": "Langqi Forge",
            "qualification": {"supplied": True, "passed": True, "path": "q.json"},
            "domains": [_domain("github"), _domain("sheet")],
            "totals": {
                "requirements": 20,
                "expected_tests": 20,
                "passed_tests": 20,
                "all_evaluations_green": True,
                "manual_interventions": 0,
                "prompt_tokens": 200,
                "completion_tokens": 40,
                "dry_run": False,
            },
            "claim_boundary": "No hidden-test guarantee.",
        }
        rendered = render_report(data)
        self.assertIn("QUALIFIED", rendered)
        self.assertIn("20 / 20", rendered)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        self.assertNotIn("<script>alert(1)</script>", rendered)
        self.assertNotIn("https://", rendered)

    def test_output_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "judge.html"
            self.assertEqual(_safe_output(path), path.resolve())
            path.write_text("preserve", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already exists"):
                _safe_output(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "preserve")

    def test_qualification_must_recompute_from_the_same_projects(self) -> None:
        payload = {
            "version": 2,
            "gate": "factory26-public-qualification-v2",
            "passed": True,
            "model_policy": {
                "allowed_models": ["qwen-plus"],
                "required_gateway_host": "dashscope.aliyuncs.com",
                "required_gateway_provenance": "alibaba-cloud-bailian",
            },
            "thresholds": {
                "github_max_seconds": 20,
                "sheet_max_seconds": 30,
            },
            "evidence": {"github_generation": {"passed": True}},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "qualification.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch(
                "factory26_harness.judge_report.qualify",
                return_value={**payload, "passed": False},
            ):
                with self.assertRaisesRegex(ValueError, "cannot be reproduced"):
                    _qualification_summary(path, root / "github", root / "sheet")


if __name__ == "__main__":
    unittest.main()
