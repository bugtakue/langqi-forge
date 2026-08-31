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
                        "requirement_count": 47,
                        "requirement_sha256": "fixture-digest",
                        "execution_route": "planner-approved-deterministic-kernel",
                        "planner_status": "completed",
                        "planner_contract": {"decision_mode": "tool_call"},
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


if __name__ == "__main__":
    unittest.main()
