from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from factory26_harness.qualification import evaluate_generation, evaluate_run


class QualificationTests(unittest.TestCase):
    def test_accepts_single_planner_call_full_green_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_path = root / "run.json"
            run_path.write_text(
                json.dumps(
                    {
                        "exit_code": 0,
                        "fixture_profile": "adversarial",
                        "fully_parallel": True,
                        "workers": 4,
                        "grep": None,
                        "duration_seconds": 9.5,
                        "stats": {
                            "expected": 101,
                            "unexpected": 0,
                            "skipped": 0,
                            "flaky": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            generation_path = root / "generation.json"
            generation_path.write_text(
                json.dumps(
                    {
                        "run_id": "11111111-1111-4111-8111-111111111111",
                        "source_identity": {"worktree_clean": True},
                        "all_local_checks_passed": True,
                        "run_completed_successfully": True,
                        "checks": [{"name": "build", "passed": True}],
                        "requirement_count": 47,
                        "requirement_sha256": "fixture-digest",
                        "execution_route": "planner-approved-deterministic-kernel",
                        "planner_status": "completed",
                        "planner_contract": {
                            "decision_mode": "tool_call",
                            "capability_tags": ["repository_lifecycle"],
                            "risks": ["permissions"],
                            "validation_focus": ["persistence"],
                        },
                        "planner_iterations": 1,
                        "coding_agent_iterations": 0,
                        "manual_interventions": 0,
                        "model_usage": {
                            "prompt_tokens": 1200,
                            "completion_tokens": 120,
                            "request_count": 1,
                            "http_attempt_count": 1,
                        },
                    }
                ),
                encoding="utf-8",
            )
            self.assertTrue(
                evaluate_run(
                    run_path,
                    expected_tests=101,
                    expected_profile="adversarial",
                    max_duration_seconds=20,
                )["passed"]
            )
            self.assertTrue(
                evaluate_generation(
                    generation_path,
                    expected_requirements=47,
                    expected_requirement_sha256="fixture-digest",
                )["passed"]
            )

    def test_rejects_skips_missing_planner_and_slow_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_path = root / "run.json"
            run_path.write_text(
                json.dumps(
                    {
                        "exit_code": 0,
                        "fixture_profile": "baseline",
                        "fully_parallel": True,
                        "workers": 1,
                        "grep": "only one test",
                        "duration_seconds": 31,
                        "stats": {
                            "expected": 100,
                            "unexpected": 0,
                            "skipped": 1,
                            "flaky": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            generation_path = root / "generation.json"
            generation_path.write_text(
                json.dumps(
                    {
                        "run_id": "not-a-run-id",
                        "source_identity": {"worktree_clean": False},
                        "all_local_checks_passed": True,
                        "run_completed_successfully": True,
                        "requirement_count": 47,
                        "requirement_sha256": "wrong-digest",
                        "execution_route": "offline-deterministic-kernel",
                        "planner_status": "skipped-dry-run",
                        "planner_contract": None,
                        "planner_iterations": 0,
                        "coding_agent_iterations": 0,
                        "manual_interventions": 0,
                        "model_usage": {
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "request_count": 0,
                            "http_attempt_count": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            self.assertFalse(
                evaluate_run(
                    run_path,
                    expected_tests=101,
                    expected_profile="baseline",
                    max_duration_seconds=20,
                )["passed"]
            )
            self.assertFalse(
                evaluate_generation(
                    generation_path,
                    expected_requirements=47,
                    expected_requirement_sha256="fixture-digest",
                )["passed"]
            )

    def test_rejects_negative_duration_and_missing_raw_playwright_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "forged.feedback.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 2,
                        "run_label": "forged",
                        "exit_code": 0,
                        "fixture_profile": "baseline",
                        "fully_parallel": True,
                        "workers": 8,
                        "grep": None,
                        "duration_seconds": -1,
                        "failure_count": 0,
                        "stats": {
                            "expected": 101,
                            "unexpected": 0,
                            "skipped": 0,
                            "flaky": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = evaluate_run(
                path,
                expected_tests=101,
                expected_profile="baseline",
                max_duration_seconds=20,
                require_bound_evidence=True,
            )
            self.assertFalse(result["passed"])
            failed = {item["name"] for item in result["checks"] if not item["passed"]}
            self.assertIn("duration_seconds_positive", failed)
            self.assertIn("raw_playwright_report_present", failed)

    def test_self_reported_green_generation_cannot_replace_bound_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report_path = root / ".arc" / "harness-report.json"
            report_path.parent.mkdir()
            report_path.write_text(
                json.dumps(
                    {
                        "version": 2,
                        "run_id": "11111111-1111-4111-8111-111111111111",
                        "source_identity": {"worktree_clean": True},
                        "duration_seconds": 1,
                        "all_local_checks_passed": True,
                        "run_completed_successfully": True,
                        "checks": [{"name": "fabricated", "passed": True}],
                        "requirement_count": 47,
                        "requirement_sha256": "fixture-digest",
                        "execution_route": "planner-approved-deterministic-kernel",
                        "planner_status": "completed",
                        "planner_contract": {
                            "domain": "github",
                            "kernel_eligible": True,
                            "decision_mode": "tool_call",
                            "capability_tags": ["repository_lifecycle"],
                            "risks": ["fabricated"],
                            "validation_focus": ["fabricated"],
                            "uncovered_requirement_ids": [],
                        },
                        "planner_iterations": 1,
                        "coding_agent_iterations": 0,
                        "manual_interventions": 0,
                        "model_usage": {
                            "prompt_tokens": 100,
                            "completion_tokens": 20,
                            "request_count": 1,
                            "http_attempt_count": 1,
                        },
                        "model_gateway": {
                            "provenance": "alibaba-cloud-bailian",
                            "endpoint_host": "dashscope.aliyuncs.com",
                            "model": "qwen-plus",
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = evaluate_generation(
                report_path,
                expected_requirements=47,
                expected_requirement_sha256="fixture-digest",
                expected_domain="github",
                require_clean_source=True,
                require_bound_artifacts=True,
            )
            self.assertFalse(result["passed"])
            failed = {item["name"] for item in result["checks"] if not item["passed"]}
            self.assertIn("bound_artifacts_readable", failed)


if __name__ == "__main__":
    unittest.main()
