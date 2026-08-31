from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from factory26_harness.qualification import evaluate_generation, evaluate_run


class QualificationTests(unittest.TestCase):
    def test_accepts_zero_token_full_green_run(self) -> None:
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
                        "stats": {"expected": 101, "unexpected": 0, "skipped": 0, "flaky": 0},
                    }
                ),
                encoding="utf-8",
            )
            generation_path = root / "generation.json"
            generation_path.write_text(
                json.dumps(
                    {
                        "all_local_checks_passed": True,
                        "requirement_count": 47,
                        "model_usage": {"prompt_tokens": 0, "completion_tokens": 0},
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
                evaluate_generation(generation_path, expected_requirements=47)["passed"]
            )

    def test_rejects_skips_tokens_and_slow_runs(self) -> None:
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
                        "stats": {"expected": 100, "unexpected": 0, "skipped": 1, "flaky": 0},
                    }
                ),
                encoding="utf-8",
            )
            generation_path = root / "generation.json"
            generation_path.write_text(
                json.dumps(
                    {
                        "all_local_checks_passed": True,
                        "requirement_count": 47,
                        "model_usage": {"prompt_tokens": 1, "completion_tokens": 0},
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
                evaluate_generation(generation_path, expected_requirements=47)["passed"]
            )


if __name__ == "__main__":
    unittest.main()
