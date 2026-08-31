from __future__ import annotations

import argparse
import json
import math
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .artifacts import canonical_json, sha256_file, verify_run_envelope
from .capabilities import capability_ids
from .capability_memory import REQUIRED_PROFILES, verify_capability_capsule
from .feedback import parse_playwright_json
from .planner import PLANNER_SYSTEM_PROMPT, PLANNER_TOOL
from .trace import verify_trace_rows


PUBLIC_REQUIREMENT_SHA256 = {
    "github": "a4ba2c2e1bd62091a46384e89a823819a485ab609780ce00ead1490edd881959",
    "sheet": "9f2bfd7a9242474ac8e5b3ab9bc0e77e7b659b0ac72b5110bddf53a313c2b494",
}
PUBLIC_TEST_BUNDLE_SHA256 = {
    "github": "7ee72cbedf9c21c6be087867512c2a6259c16f4cdbf0969f46203c7f3d07ed77",
    "sheet": "afec335ed4d442795b344cd6b67f27bdc28583ed0b5ca13876e5acb3a4778f43",
}
BAILIAN_EVIDENCE_MODELS = (
    "qwen-plus",
    "qwen-max",
    "qwen-coder-plus",
    "qwen2.5-coder-32b-instruct",
    "qwen3-coder-plus",
    "qwen3-coder-flash",
)
QUALIFIED_KERNEL_ROUTES = frozenset(
    {
        "planner-approved-deterministic-kernel",
        "planner-approved-capability-memory-kernel",
    }
)
FORCED_PLANNER_TOOL_CHOICE = {
    "type": "function",
    "function": {"name": "select_build_contract"},
}
CONTRACT_FIELDS = (
    "domain",
    "kernel_eligible",
    "capability_tags",
    "risks",
    "validation_focus",
    "rationale",
    "uncovered_requirement_ids",
)


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _digest(path: Path) -> str:
    return sha256_file(path)


def _check(name: str, passed: bool, actual: Any, expected: Any) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "actual": actual,
        "expected": expected,
    }


def _positive_finite(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def _contains_truncation(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_truncation(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_truncation(child) for child in value)
    return isinstance(value, str) and "[TRUNCATED sha256=" in value


def evaluate_run(
    path: Path,
    *,
    expected_tests: int,
    expected_profile: str,
    max_duration_seconds: float,
    expected_source_run_id: str | None = None,
    minimum_workers: int = 4,
    expected_application_source_sha256: str | None = None,
    expected_test_bundle_sha256: str | None = None,
    expected_requirement_sha256: str | None = None,
    require_bound_evidence: bool = False,
) -> dict[str, Any]:
    payload = _load(path)
    stats = payload.get("stats") or {}
    duration = payload.get("duration_seconds")
    checks = [
        _check(
            "source_run_id",
            expected_source_run_id is None
            or payload.get("source_run_id") == expected_source_run_id,
            payload.get("source_run_id"),
            expected_source_run_id,
        ),
        _check("exit_code", payload.get("exit_code") == 0, payload.get("exit_code"), 0),
        _check(
            "fixture_profile",
            payload.get("fixture_profile") == expected_profile,
            payload.get("fixture_profile"),
            expected_profile,
        ),
        _check(
            "fully_parallel",
            payload.get("fully_parallel") is True,
            payload.get("fully_parallel"),
            True,
        ),
        _check(
            "minimum_workers",
            int(payload.get("workers") or 0) >= minimum_workers,
            payload.get("workers"),
            {"minimum": minimum_workers},
        ),
        _check("unfiltered", payload.get("grep") is None, payload.get("grep"), None),
        _check(
            "expected_tests",
            stats.get("expected") == expected_tests,
            stats.get("expected"),
            expected_tests,
        ),
        _check("unexpected", stats.get("unexpected", 0) == 0, stats.get("unexpected", 0), 0),
        _check("skipped", stats.get("skipped", 0) == 0, stats.get("skipped", 0), 0),
        _check("flaky", stats.get("flaky", 0) == 0, stats.get("flaky", 0), 0),
        _check(
            "duration_seconds_positive",
            _positive_finite(duration),
            duration,
            {"exclusive_minimum": 0},
        ),
        _check(
            "duration_seconds_maximum",
            _positive_finite(duration) and float(duration) <= max_duration_seconds,
            duration,
            {"maximum": max_duration_seconds},
        ),
    ]
    if require_bound_evidence:
        label = str(payload.get("run_label") or "")
        raw_path = path.parent / f"{label}.playwright.json"
        try:
            raw = _load(raw_path)
            raw_failures = parse_playwright_json(raw)
            raw_stats = raw.get("stats") or {}
            raw_sha256 = _digest(raw_path)
            checks.extend(
                [
                    _check("feedback_version", payload.get("version") == 2, payload.get("version"), 2),
                    _check("raw_playwright_report_present", True, str(raw_path), "present JSON report"),
                    _check("raw_playwright_report_sha256", payload.get("playwright_report_sha256") == raw_sha256, payload.get("playwright_report_sha256"), raw_sha256),
                    _check("raw_stats_match_feedback", canonical_json(raw_stats) == canonical_json(stats), stats, raw_stats),
                    _check("raw_failure_count", payload.get("failure_count") == len(raw_failures) == 0, payload.get("failure_count"), 0),
                    _check("application_source_binding", payload.get("application_source_sha256") == expected_application_source_sha256, payload.get("application_source_sha256"), expected_application_source_sha256),
                    _check("locked_test_bundle", payload.get("test_bundle_sha256") == expected_test_bundle_sha256, payload.get("test_bundle_sha256"), expected_test_bundle_sha256),
                    _check("public_requirement_binding", payload.get("requirements_sha256") == expected_requirement_sha256, payload.get("requirements_sha256"), expected_requirement_sha256),
                ]
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            checks.append(
                _check(
                    "raw_playwright_report_present",
                    False,
                    str(exc),
                    "present JSON report with matching hash and statistics",
                )
            )
    return {
        "path": str(path),
        "sha256": _digest(path),
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
    }


def _valid_run_id(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def _contract_arguments(response: dict[str, Any]) -> tuple[dict[str, Any] | None, Any]:
    message = response.get("message") or {}
    calls = message.get("tool_calls") or []
    if not isinstance(calls, list) or len(calls) != 1:
        return None, calls
    function = calls[0].get("function") or {}
    if function.get("name") != "select_build_contract":
        return None, calls
    raw = function.get("arguments")
    try:
        arguments = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, raw
    return arguments if isinstance(arguments, dict) else None, raw


def _trace_checks(
    path: Path,
    *,
    expected_run_id: str,
    expected_public_evaluations: int,
    report: dict[str, Any],
    expected_gateway_host: str | None,
    expected_gateway_provenance: str | None,
) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        return [_check("trace_readable", False, str(exc), "valid JSONL production trace")]

    events = [str(row.get("event") or "") for row in rows]
    trace_integrity = verify_trace_rows(rows, require_fully_sealed=True)
    sequences = [row.get("sequence") for row in rows]
    payloads: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        payload = row.get("payload")
        payloads.setdefault(str(row.get("event") or ""), []).append(
            payload if isinstance(payload, dict) else {}
        )
    requests = payloads.get("model_request", [])
    responses = payloads.get("model_response", [])
    tool_calls = payloads.get("agent_tool_call", [])
    interventions = payloads.get("human_intervention_checkpoint", [])
    starts = payloads.get("run_started", [])
    completions = payloads.get("run_completed", [])
    sessions_started = payloads.get("agent_session_started", [])
    sessions_completed = payloads.get("agent_session_completed", [])
    request_payload = (requests[0].get("payload") or {}) if len(requests) == 1 else {}
    messages = request_payload.get("messages") or []
    request_tools = request_payload.get("tools") or []
    response = responses[0] if len(responses) == 1 else {}
    response_id = response.get("response_id")
    arguments, raw_calls = _contract_arguments(response)
    tool_arguments = tool_calls[0].get("arguments") if len(tool_calls) == 1 else None
    contract = report.get("planner_contract") or {}
    expected_contract_arguments = {field: contract.get(field) for field in CONTRACT_FIELDS}
    validation_payloads = payloads.get("validation_result", [])
    final_validation_by_tool: dict[str, Any] = {}
    for validation in validation_payloads:
        final_validation_by_tool[str(validation.get("tool") or "")] = validation.get("result")
    report_checks = {
        str(item.get("name") or ""): item
        for item in report.get("checks") or []
        if isinstance(item, dict)
    }
    gateway = report.get("model_gateway") or {}
    endpoint = str(requests[0].get("endpoint") or "") if len(requests) == 1 else ""
    endpoint_parts = urlsplit(endpoint)
    endpoint_host = (endpoint_parts.hostname or "").lower()
    forbidden = sorted(
        {
            event
            for event in events
            if event
            in {
                "run_failed",
                "planner_failed",
                "model_error",
                "agent_session_stalled",
                "agent_session_exhausted",
                "public_evaluation_failed",
            }
        }
    )
    user_message = messages[1].get("content") if len(messages) == 2 and isinstance(messages[1], dict) else None
    checks = [
        _check("trace_readable", True, True, True),
        _check("trace_integrity_fully_sealed", trace_integrity.get("valid") is True, trace_integrity, {"valid": True, "sealed_rows": len(rows)}),
        _check("trace_sequence_contiguous", sequences == list(range(1, len(rows) + 1)), sequences, f"1..{len(rows)}"),
        _check("trace_run_started_once", len(starts) == 1, len(starts), 1),
        _check("trace_run_id_binding", len(starts) == 1 and starts[0].get("run_id") == expected_run_id, starts[0].get("run_id") if len(starts) == 1 else None, expected_run_id),
        _check("trace_model_request_once", len(requests) == 1, len(requests), 1),
        _check("trace_model_response_once", len(responses) == 1, len(responses), 1),
        _check("trace_model_response_id", bool(response_id), response_id, "non-empty provider response id"),
        _check("trace_planner_messages_complete", len(messages) == 2 and messages[0] == {"role": "system", "content": PLANNER_SYSTEM_PROMPT} and isinstance(messages[1], dict) and messages[1].get("role") == "user" and bool(user_message) and not _contains_truncation(messages), messages, "exact system prompt plus complete user digest"),
        _check("trace_planner_tool_schema_exact", canonical_json(request_tools) == canonical_json([PLANNER_TOOL]), request_tools, [PLANNER_TOOL]),
        _check("trace_planner_tool_forced", request_payload.get("tool_choice") == FORCED_PLANNER_TOOL_CHOICE, request_payload.get("tool_choice"), FORCED_PLANNER_TOOL_CHOICE),
        _check("trace_agent_session_started_once", len(sessions_started) == 1 and sessions_started[0].get("stage") == "specification_planning" and sessions_started[0].get("prompt") == user_message, sessions_started, "one specification-planning session bound to the model prompt"),
        _check("trace_agent_session_completed_once", len(sessions_completed) == 1 and sessions_completed[0].get("stage") == "specification_planning" and canonical_json(sessions_completed[0].get("contract")) == canonical_json(contract), sessions_completed, "one completed specification-planning session bound to the report contract"),
        _check("trace_agent_tool_call_once", len(tool_calls) == 1, len(tool_calls), 1),
        _check("trace_model_tool_call_exact", arguments is not None and canonical_json(arguments) == canonical_json(expected_contract_arguments), arguments if arguments is not None else raw_calls, expected_contract_arguments),
        _check("trace_applied_tool_call_exact", len(tool_calls) == 1 and tool_calls[0].get("tool") == "select_build_contract" and tool_calls[0].get("decision_mode") == "tool_call" and canonical_json(tool_arguments) == canonical_json(arguments), tool_calls[0] if len(tool_calls) == 1 else None, {"tool": "select_build_contract", "arguments": arguments, "decision_mode": "tool_call"}),
        _check("trace_human_checkpoint", len(interventions) == 1 and interventions[0].get("intervention_required") is False and interventions[0].get("intervention_count") == 0, interventions, [{"intervention_required": False, "intervention_count": 0}]),
        _check("trace_validation_layers", len(validation_payloads) >= 3, len(validation_payloads), {"minimum": 3}),
        _check("trace_all_validations_passed", bool(validation_payloads) and all((item.get("result") or {}).get("passed") is True for item in validation_payloads), [item.get("result") for item in validation_payloads], "every recorded validation passed"),
        _check("trace_final_validations_match_report", bool(report_checks) and set(final_validation_by_tool) == set(report_checks) and all(canonical_json(final_validation_by_tool[name]) == canonical_json(report_checks[name]) for name in report_checks), final_validation_by_tool, report_checks),
        _check("trace_run_completed_once", len(completions) == 1, len(completions), 1),
        _check("trace_completed_report_exact", len(completions) == 1 and canonical_json(completions[0].get("report")) == canonical_json(report), completions[0].get("report") if len(completions) == 1 else None, report),
        _check("trace_public_evaluations", len(payloads.get("public_evaluation_completed", [])) == expected_public_evaluations, len(payloads.get("public_evaluation_completed", [])), expected_public_evaluations),
        _check("trace_no_failure_events", not forbidden, forbidden, []),
        _check("trace_not_truncated", not _contains_truncation(rows), _contains_truncation(rows), False),
        _check("model_https_endpoint", endpoint_parts.scheme == "https" and bool(endpoint_host), endpoint, "https://<platform-model-gateway>/..."),
        _check("gateway_endpoint_host_binding", endpoint_host == str(gateway.get("endpoint_host") or "").lower(), endpoint_host, str(gateway.get("endpoint_host") or "").lower()),
        _check("gateway_binding_request", len(requests) == 1 and requests[0].get("gateway") == gateway and requests[0].get("model") == gateway.get("model"), requests[0] if len(requests) == 1 else None, gateway),
        _check("gateway_binding_response", len(responses) == 1 and responses[0].get("gateway") == gateway and responses[0].get("model") == gateway.get("model"), responses[0] if len(responses) == 1 else None, gateway),
    ]
    if expected_gateway_host:
        normalized_host = expected_gateway_host.strip().lower()
        checks.append(
            _check(
                "required_gateway_host",
                endpoint_host == normalized_host,
                endpoint_host,
                normalized_host,
            )
        )
    if expected_gateway_provenance:
        checks.append(
            _check(
                "required_gateway_provenance",
                gateway.get("provenance") == expected_gateway_provenance,
                gateway.get("provenance"),
                expected_gateway_provenance,
            )
        )
    return checks


def _artifact_checks(
    report_path: Path,
    *,
    expected_domain: str,
    expected_requirements: int,
    expected_public_evaluations: int,
) -> list[dict[str, Any]]:
    root = report_path.parent.parent
    try:
        envelope = verify_run_envelope(root)
        report = _load(report_path)
        planner = _load(root / ".arc" / "planner-contract.json")
        plan = _load(root / ".arc" / "compiled-plan.json")
        coverage = _load(root / ".arc" / "capability-coverage.json")
        capsule = verify_capability_capsule(
            root / ".arc" / "capability-capsule.json"
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [_check("bound_artifacts_readable", False, str(exc), "valid cross-bound run envelope")]
    contract = report.get("planner_contract") or {}
    report_coverage = report.get("capability_coverage") or {}
    requirements = report_coverage.get("requirements") or []
    required = set(report_coverage.get("required_capabilities") or [])
    allowed = set(capability_ids(expected_domain, implemented_only=True))
    tags = set(contract.get("capability_tags") or [])
    source = envelope.get("application_source") or {}
    capsule_capabilities = {
        str(item.get("id") or "")
        for item in capsule.get("capabilities") or []
        if isinstance(item, dict)
    }
    return [
        _check("bound_artifacts_readable", True, True, True),
        _check("run_envelope_version", envelope.get("version") == 2, envelope.get("version"), 2),
        _check("run_envelope_id", envelope.get("run_id") == report.get("run_id"), envelope.get("run_id"), report.get("run_id")),
        _check("run_envelope_public_evaluations", len(envelope.get("evaluations") or []) == expected_public_evaluations, len(envelope.get("evaluations") or []), expected_public_evaluations),
        _check("application_source_present", source.get("file_count", 0) > 0 and bool(source.get("sha256")), source, "non-empty frontend/backend manifest"),
        _check("capability_capsule_run_binding", capsule.get("source_run_id") == report.get("run_id") and (capsule.get("application_source") or {}).get("sha256") == source.get("sha256"), {"run_id": capsule.get("source_run_id"), "source": (capsule.get("application_source") or {}).get("sha256")}, {"run_id": report.get("run_id"), "source": source.get("sha256")}),
        _check("capability_capsule_profile_gate", set((capsule.get("promotion_gate") or {}).get("observed_profiles") or []) >= set(REQUIRED_PROFILES[expected_domain]), (capsule.get("promotion_gate") or {}).get("observed_profiles"), sorted(REQUIRED_PROFILES[expected_domain])),
        _check("planner_contract_file_binding", planner.get("run_id") == report.get("run_id") and planner.get("status") == report.get("planner_status") and planner.get("execution_route") == report.get("execution_route") and canonical_json(planner.get("contract")) == canonical_json(contract), planner, "exact report planner fields"),
        _check("compiled_plan_binding", plan.get("run_id") == report.get("run_id") and plan.get("detected_domain") == report.get("detected_domain") and plan.get("requirement_sha256") == report.get("requirement_sha256") and plan.get("planner_status") == report.get("planner_status") and plan.get("execution_route") == report.get("execution_route") and canonical_json(plan.get("planner_contract")) == canonical_json(contract), plan, "exact report planning fields"),
        _check("coverage_file_binding", canonical_json(coverage) == canonical_json(report_coverage) == canonical_json(plan.get("capability_coverage")), coverage, report_coverage),
        _check("coverage_domain", report_coverage.get("domain") == expected_domain and contract.get("domain") == expected_domain, {"coverage": report_coverage.get("domain"), "contract": contract.get("domain")}, expected_domain),
        _check("coverage_kernel_eligible", report_coverage.get("kernel_eligible") is True and contract.get("kernel_eligible") is True, {"coverage": report_coverage.get("kernel_eligible"), "contract": contract.get("kernel_eligible")}, True),
        _check("coverage_closed_world", report_coverage.get("uncovered_requirement_ids") == [] and report_coverage.get("missing_capabilities") == [] and len(requirements) == expected_requirements and all(isinstance(item, dict) and item.get("implemented") is True for item in requirements), {"requirements": len(requirements), "uncovered": report_coverage.get("uncovered_requirement_ids"), "missing": report_coverage.get("missing_capabilities")}, {"requirements": expected_requirements, "uncovered": [], "missing": []}),
        _check("coverage_capabilities_legal", bool(required) and required <= allowed and required <= tags and tags <= allowed, {"required": sorted(required), "planner_tags": sorted(tags)}, {"allowed": sorted(allowed), "planner_covers_all_required": True}),
        _check("capability_capsule_covers_required", required <= capsule_capabilities, sorted(capsule_capabilities), sorted(required)),
    ]


def evaluate_generation(
    path: Path,
    *,
    expected_requirements: int,
    expected_requirement_sha256: str | None = None,
    max_prompt_tokens: int = 6_000,
    max_completion_tokens: int = 1_000,
    trace_path: Path | None = None,
    expected_public_evaluations: int = 0,
    expected_domain: str | None = None,
    allowed_models: tuple[str, ...] | None = None,
    expected_gateway_host: str | None = None,
    expected_gateway_provenance: str | None = None,
    require_clean_source: bool = False,
    require_bound_artifacts: bool = False,
) -> dict[str, Any]:
    payload = _load(path)
    usage = payload.get("model_usage") or {}
    contract = payload.get("planner_contract") or {}
    source_identity = payload.get("source_identity") or {}
    gateway = payload.get("model_gateway") or {}
    model_name = str(gateway.get("model") or "").strip()
    endpoint_host = str(gateway.get("endpoint_host") or "").strip().lower()
    gateway_provenance = str(gateway.get("provenance") or "").strip()
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    clean_expected: Any = True if require_clean_source else "true or unavailable"
    clean_passed = source_identity.get("worktree_clean") is True if require_clean_source else source_identity.get("worktree_clean") is not False
    checks = [
        _check("report_version", payload.get("version") == 2 if require_bound_artifacts else payload.get("version") in {None, 1, 2}, payload.get("version"), 2 if require_bound_artifacts else "1 or 2"),
        _check("run_id", _valid_run_id(payload.get("run_id")), payload.get("run_id"), "UUID"),
        _check("source_worktree_clean", clean_passed, source_identity.get("worktree_clean"), clean_expected),
        _check("all_local_checks_passed", payload.get("all_local_checks_passed") is True, payload.get("all_local_checks_passed"), True),
        _check("run_completed_successfully", payload.get("run_completed_successfully") is True, payload.get("run_completed_successfully"), True),
        _check("local_checks_nonempty_and_green", bool(payload.get("checks")) and all(isinstance(item, dict) and item.get("passed") is True for item in payload.get("checks") or []), payload.get("checks"), "one or more passed checks"),
        _check("duration_seconds_positive", _positive_finite(payload.get("duration_seconds")) if require_bound_artifacts else True, payload.get("duration_seconds"), {"exclusive_minimum": 0}),
        _check("requirement_count", payload.get("requirement_count") == expected_requirements, payload.get("requirement_count"), expected_requirements),
        _check("requirement_sha256", expected_requirement_sha256 is None or payload.get("requirement_sha256") == expected_requirement_sha256, payload.get("requirement_sha256"), expected_requirement_sha256),
        _check("planner_status", payload.get("planner_status") == "completed", payload.get("planner_status"), "completed"),
        _check("execution_route", payload.get("execution_route") in QUALIFIED_KERNEL_ROUTES, payload.get("execution_route"), sorted(QUALIFIED_KERNEL_ROUTES)),
        _check("planner_decision_mode", contract.get("decision_mode") == "tool_call", contract.get("decision_mode"), "tool_call"),
        _check("planner_capabilities_present", bool(contract.get("capability_tags")), contract.get("capability_tags"), "one or more versioned capabilities"),
        _check("planner_risks_present", bool(contract.get("risks")), contract.get("risks"), "one or more bounded risks"),
        _check("planner_validation_focus_present", bool(contract.get("validation_focus")), contract.get("validation_focus"), "one or more validation priorities"),
        _check("model_request_count", usage.get("request_count") == 1, usage.get("request_count"), 1),
        _check("model_http_attempt_count", usage.get("http_attempt_count") == 1, usage.get("http_attempt_count"), 1),
        _check("prompt_tokens", 0 < prompt_tokens <= max_prompt_tokens, prompt_tokens, {"minimum": 1, "maximum": max_prompt_tokens}),
        _check("completion_tokens", 0 < completion_tokens <= max_completion_tokens, completion_tokens, {"minimum": 1, "maximum": max_completion_tokens}),
        _check("planner_iterations", payload.get("planner_iterations") == 1, payload.get("planner_iterations"), 1),
        _check("coding_agent_iterations", payload.get("coding_agent_iterations") == 0, payload.get("coding_agent_iterations"), 0),
        _check("manual_interventions", payload.get("manual_interventions") == 0, payload.get("manual_interventions"), 0),
        _check("model_gateway_metadata", (not require_bound_artifacts) or (bool(model_name) and bool(endpoint_host) and bool(gateway_provenance)), gateway, "non-empty model, endpoint_host, and inferred provenance"),
        _check("qualified_model", (not require_bound_artifacts) or not allowed_models or model_name in allowed_models, model_name, list(allowed_models) if allowed_models else "non-empty platform-injected model"),
        _check("required_gateway_host_metadata", (not require_bound_artifacts) or not expected_gateway_host or endpoint_host == expected_gateway_host.strip().lower(), endpoint_host, expected_gateway_host.strip().lower() if expected_gateway_host else "any HTTPS platform gateway"),
        _check("required_gateway_provenance_metadata", (not require_bound_artifacts) or not expected_gateway_provenance or gateway_provenance == expected_gateway_provenance, gateway_provenance, expected_gateway_provenance or "inferred from endpoint host"),
    ]
    if require_bound_artifacts:
        if expected_domain is None:
            raise ValueError("expected_domain is required for bound artifact qualification")
        checks.extend(
            _artifact_checks(
                path,
                expected_domain=expected_domain,
                expected_requirements=expected_requirements,
                expected_public_evaluations=expected_public_evaluations,
            )
        )
    if trace_path is not None:
        checks.extend(
            _trace_checks(
                trace_path,
                expected_run_id=str(payload.get("run_id") or ""),
                expected_public_evaluations=expected_public_evaluations,
                report=payload,
                expected_gateway_host=expected_gateway_host,
                expected_gateway_provenance=expected_gateway_provenance,
            )
        )
    return {
        "path": str(path),
        "sha256": _digest(path),
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
    }


def qualify(
    github_project: Path,
    sheet_project: Path,
    *,
    github_max_seconds: float = 20.0,
    sheet_max_seconds: float = 30.0,
    allowed_models: tuple[str, ...] | None = None,
    expected_gateway_host: str | None = None,
    expected_gateway_provenance: str | None = None,
) -> dict[str, Any]:
    github_root = github_project.resolve()
    sheet_root = sheet_project.resolve()
    github_report = _load(github_root / ".arc" / "harness-report.json")
    sheet_report = _load(sheet_root / ".arc" / "harness-report.json")
    github_run_id = str(github_report.get("run_id") or "")
    sheet_run_id = str(sheet_report.get("run_id") or "")
    github_source = (github_report.get("application_source") or {}).get("sha256")
    sheet_source = (sheet_report.get("application_source") or {}).get("sha256")
    evidence = {
        "github_generation": evaluate_generation(
            github_root / ".arc" / "harness-report.json",
            expected_requirements=47,
            expected_requirement_sha256=PUBLIC_REQUIREMENT_SHA256["github"],
            trace_path=github_root / ".arc" / "production-trace.jsonl",
            expected_public_evaluations=2,
            expected_domain="github",
            allowed_models=allowed_models,
            expected_gateway_host=expected_gateway_host,
            expected_gateway_provenance=expected_gateway_provenance,
            require_clean_source=True,
            require_bound_artifacts=True,
        ),
        "sheet_generation": evaluate_generation(
            sheet_root / ".arc" / "harness-report.json",
            expected_requirements=24,
            expected_requirement_sha256=PUBLIC_REQUIREMENT_SHA256["sheet"],
            trace_path=sheet_root / ".arc" / "production-trace.jsonl",
            expected_public_evaluations=1,
            expected_domain="sheet",
            allowed_models=allowed_models,
            expected_gateway_host=expected_gateway_host,
            expected_gateway_provenance=expected_gateway_provenance,
            require_clean_source=True,
            require_bound_artifacts=True,
        ),
        "github_baseline": evaluate_run(
            github_root / ".arc" / "public-eval" / "github.feedback.json",
            expected_tests=101,
            expected_profile="baseline",
            max_duration_seconds=github_max_seconds,
            expected_source_run_id=github_run_id,
            expected_application_source_sha256=github_source,
            expected_test_bundle_sha256=PUBLIC_TEST_BUNDLE_SHA256["github"],
            expected_requirement_sha256=PUBLIC_REQUIREMENT_SHA256["github"],
            require_bound_evidence=True,
        ),
        "github_adversarial": evaluate_run(
            github_root / ".arc" / "public-eval" / "github.adversarial.feedback.json",
            expected_tests=101,
            expected_profile="adversarial",
            max_duration_seconds=github_max_seconds,
            expected_source_run_id=github_run_id,
            expected_application_source_sha256=github_source,
            expected_test_bundle_sha256=PUBLIC_TEST_BUNDLE_SHA256["github"],
            expected_requirement_sha256=PUBLIC_REQUIREMENT_SHA256["github"],
            require_bound_evidence=True,
        ),
        "sheet_baseline": evaluate_run(
            sheet_root / ".arc" / "public-eval" / "sheet.feedback.json",
            expected_tests=102,
            expected_profile="baseline",
            max_duration_seconds=sheet_max_seconds,
            expected_source_run_id=sheet_run_id,
            expected_application_source_sha256=sheet_source,
            expected_test_bundle_sha256=PUBLIC_TEST_BUNDLE_SHA256["sheet"],
            expected_requirement_sha256=PUBLIC_REQUIREMENT_SHA256["sheet"],
            require_bound_evidence=True,
        ),
    }
    display_paths = {
        "github_generation": ".arc/harness-report.json",
        "sheet_generation": ".arc/harness-report.json",
        "github_baseline": ".arc/public-eval/github.feedback.json",
        "github_adversarial": ".arc/public-eval/github.adversarial.feedback.json",
        "sheet_baseline": ".arc/public-eval/sheet.feedback.json",
    }
    for name, display_path in display_paths.items():
        evidence[name]["path"] = display_path
    return {
        "version": 2,
        "generated_at": datetime.now(UTC).isoformat(),
        "gate": "factory26-public-qualification-v2",
        "claim_boundary": (
            "This gate verifies internal cross-binding, locked public tests, and a "
            "declared HTTPS model route. Official platform metering remains the external "
            "authority; optional provider pins are metadata checks, not hardware attestation."
        ),
        "model_policy": {
            "allowed_models": list(allowed_models) if allowed_models else None,
            "required_gateway_host": expected_gateway_host,
            "required_gateway_provenance": expected_gateway_provenance,
        },
        "thresholds": {
            "github_max_seconds": github_max_seconds,
            "sheet_max_seconds": sheet_max_seconds,
        },
        "passed": all(item["passed"] for item in evidence.values()),
        "evidence": evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed Factory26 public qualification gate"
    )
    parser.add_argument("--github-project", type=Path, required=True)
    parser.add_argument("--sheet-project", type=Path, required=True)
    parser.add_argument("--github-max-seconds", type=float, default=20.0)
    parser.add_argument("--sheet-max-seconds", type=float, default=30.0)
    parser.add_argument("--allowed-model", action="append", dest="allowed_models")
    parser.add_argument(
        "--bailian-evidence-profile",
        action="store_true",
        help="Pin the optional self-published evidence run to the supported Bailian route and Qwen model allowlist",
    )
    parser.add_argument(
        "--require-gateway-host",
        help="Optionally pin evidence to one HTTPS gateway host, for example dashscope.aliyuncs.com",
    )
    parser.add_argument(
        "--require-provider-provenance",
        help="Optionally pin inferred provider provenance, for example alibaba-cloud-bailian",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    environment_models = tuple(
        item.strip()
        for item in os.environ.get("FACTORY26_QUALIFIED_MODELS", "").split(",")
        if item.strip()
    )
    allowed_models = tuple(
        args.allowed_models
        or environment_models
        or (BAILIAN_EVIDENCE_MODELS if args.bailian_evidence_profile else ())
    ) or None
    expected_gateway_host = args.require_gateway_host or (
        "dashscope.aliyuncs.com" if args.bailian_evidence_profile else None
    )
    expected_gateway_provenance = args.require_provider_provenance or (
        "alibaba-cloud-bailian" if args.bailian_evidence_profile else None
    )
    report = qualify(
        args.github_project,
        args.sheet_project,
        github_max_seconds=args.github_max_seconds,
        sheet_max_seconds=args.sheet_max_seconds,
        allowed_models=allowed_models,
        expected_gateway_host=expected_gateway_host,
        expected_gateway_provenance=expected_gateway_provenance,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(args.output)
    print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
