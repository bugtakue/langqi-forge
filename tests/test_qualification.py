from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from factory26_harness.planner import (
    PLANNER_SYSTEM_PROMPT,
    contract_arguments_sha256,
    normalize_contract_arguments,
    planner_tool_schema,
)
from factory26_harness.qualification import (
    FORCED_PLANNER_TOOL_CHOICE,
    _trace_checks,
    evaluate_generation,
    evaluate_run,
)
from factory26_harness.trace import ProductionTrace, reseal_trace_rows


class QualificationTests(unittest.TestCase):
    def test_trace_gate_replays_raw_tool_argument_normalization(self) -> None:
        run_id = "11111111-1111-4111-8111-111111111111"
        raw_arguments = {
            "domain": "github",
            "kernel_eligible": True,
            "capability_tags": ["repository_lifecycle"],
            "risks": ["r" * 140],
            "validation_focus": ["v" * 140],
            "rationale": "reason " * 80,
            "uncovered_requirement_ids": [],
        }
        contract = normalize_contract_arguments(
            raw_arguments, known_requirement_ids={"R1"}
        ).as_dict()
        applied_arguments = {
            key: contract[key]
            for key in (
                "domain",
                "kernel_eligible",
                "capability_tags",
                "risks",
                "validation_focus",
                "rationale",
                "uncovered_requirement_ids",
            )
        }
        gateway = {
            "provenance": "alibaba-cloud-bailian",
            "endpoint_host": "dashscope.aliyuncs.com",
            "model": "qwen-plus",
        }
        checks = [
            {"name": name, "passed": True}
            for name in ("structure", "build", "startup")
        ]
        report = {
            "run_id": run_id,
            "detected_domain": "github",
            "planner_contract": contract,
            "capability_coverage": {
                "requirements": [{"requirement_id": "R1"}]
            },
            "model_gateway": gateway,
            "checks": checks,
        }
        prompt = "candidate contract"
        message = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "planner-1",
                    "type": "function",
                    "function": {
                        "name": "select_build_contract",
                        "arguments": json.dumps(raw_arguments),
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            trace_path = Path(temporary) / "production-trace.jsonl"
            trace = ProductionTrace(trace_path)
            trace.record("run_started", run_id=run_id)
            trace.record(
                "agent_session_started",
                stage="specification_planning",
                prompt=prompt,
            )
            trace.record(
                "model_request",
                endpoint="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                model="qwen-plus",
                gateway=gateway,
                payload={
                    "messages": [
                        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "tools": [planner_tool_schema("github")],
                    "tool_choice": FORCED_PLANNER_TOOL_CHOICE,
                },
            )
            trace.record(
                "model_response",
                model="qwen-plus",
                gateway=gateway,
                response_id="response-1",
                message=message,
            )
            trace.record(
                "agent_tool_call",
                tool="select_build_contract",
                arguments=applied_arguments,
                raw_arguments_sha256=contract_arguments_sha256(raw_arguments),
                decision_mode="tool_call",
            )
            trace.record(
                "agent_session_completed",
                stage="specification_planning",
                contract=contract,
            )
            trace.record(
                "human_intervention_checkpoint",
                intervention_required=False,
                intervention_count=0,
            )
            for result in checks:
                trace.record("validation_result", tool=result["name"], result=result)
            trace.record("run_completed", report=report)
            results = _trace_checks(
                trace_path,
                expected_run_id=run_id,
                expected_public_evaluations=0,
                report=report,
                expected_gateway_host="dashscope.aliyuncs.com",
                expected_gateway_provenance="alibaba-cloud-bailian",
                expected_user_message_sha256=hashlib.sha256(
                    prompt.encode("utf-8")
                ).hexdigest(),
            )
            self.assertTrue(
                all(result["passed"] for result in results),
                [result for result in results if not result["passed"]],
            )

            rows = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
            ]
            response = next(
                row for row in rows if row["event"] == "model_response"
            )
            function = response["payload"]["message"]["tool_calls"][0]["function"]
            tampered = json.loads(function["arguments"])
            tampered["rationale"] += " hidden-tail-tampering"
            function["arguments"] = json.dumps(tampered)
            request = next(row for row in rows if row["event"] == "model_request")
            request["payload"]["payload"]["messages"][1]["content"] += " tampered"
            trace_path.write_text(
                "\n".join(
                    json.dumps(row, ensure_ascii=False, sort_keys=True)
                    for row in reseal_trace_rows(rows)
                )
                + "\n",
                encoding="utf-8",
            )
            tampered_results = _trace_checks(
                trace_path,
                expected_run_id=run_id,
                expected_public_evaluations=0,
                report=report,
                expected_gateway_host="dashscope.aliyuncs.com",
                expected_gateway_provenance="alibaba-cloud-bailian",
                expected_user_message_sha256=hashlib.sha256(
                    prompt.encode("utf-8")
                ).hexdigest(),
            )
        by_name = {result["name"]: result for result in tampered_results}
        self.assertFalse(by_name["trace_planner_user_prompt_locked"]["passed"])
        self.assertTrue(by_name["trace_model_tool_call_normalizes_exactly"]["passed"])
        self.assertFalse(by_name["trace_model_tool_call_raw_hash"]["passed"])

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
                expected_task_id="github",
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
