from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .impact import ChangeImpactGraph


REQ_ID_PATTERN = re.compile(r"\bREQ-[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)*\b")
LOCATOR_PATTERN = re.compile(r"(?:Locator:|waiting for)\s*([^\n]+)", re.IGNORECASE)
ERROR_PATTERN = re.compile(r"(?:Error:|AssertionError:)\s*([^\n]+)", re.IGNORECASE)
INFRASTRUCTURE_PATTERN = re.compile(
    r"browser\.newcontext|protocol error|test ended|while setting up|browser (?:closed|disconnected)|worker process exited",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PlaywrightFailure:
    test_id: str
    title: str
    file: str
    requirement_id: str | None
    error: str
    signature: str


def _walk_suites(suites: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for suite in suites:
        if not isinstance(suite, dict):
            continue
        yield suite
        yield from _walk_suites(suite.get("suites") or [])


def validate_playwright_report(
    payload: dict[str, Any],
    *,
    expected_test_files: set[str] | None,
    expected_test_count: int,
    expected_inventory_sha256: str,
    expected_workers: int | None = None,
    expected_fully_parallel: bool | None = None,
) -> dict[str, Any]:
    """Validate the enumerated raw result set, not only Playwright's counters."""

    if not isinstance(payload, dict):
        raise ValueError("Playwright report must be an object")
    suites = payload.get("suites")
    if not isinstance(suites, list) or not suites:
        raise ValueError("Playwright report has no suites")
    root_errors = payload.get("errors") or []
    if not isinstance(root_errors, list) or root_errors:
        raise ValueError("Playwright report contains root-level errors")

    inventory: list[dict[str, Any]] = []
    observed_statuses: Counter[str] = Counter()
    observed_files: set[str] = set()
    observed_ids: set[str] = set()
    for suite in _walk_suites(suites):
        suite_file = str(suite.get("file") or "")
        specs = suite.get("specs") or []
        if not isinstance(specs, list):
            raise ValueError("Playwright suite specs must be an array")
        for spec in specs:
            if not isinstance(spec, dict):
                raise ValueError("Playwright report contains a non-object spec")
            test_id = str(spec.get("id") or "").strip()
            title = str(spec.get("title") or "").strip()
            file_path = str(spec.get("file") or suite_file).strip()
            safe_file = PurePosixPath(file_path)
            if (
                not test_id
                or not title
                or not file_path
                or safe_file.is_absolute()
                or ".." in safe_file.parts
            ):
                raise ValueError("Playwright report contains an unsafe test identity")
            tests = spec.get("tests") or []
            if not isinstance(tests, list) or len(tests) != 1:
                raise ValueError(
                    "Playwright report requires exactly one configured project per spec"
                )
            test = tests[0]
            if not isinstance(test, dict):
                raise ValueError("Playwright report contains a non-object test")
            project_id = str(test.get("projectId") or "").strip()
            project_name = str(test.get("projectName") or "").strip()
            if (
                test.get("expectedStatus") != "passed"
                or not project_id
                or not project_name
            ):
                raise ValueError("Playwright test project or expected status is invalid")
            status = str(test.get("status") or "").strip()
            if status not in {"expected", "unexpected", "skipped", "flaky"}:
                raise ValueError(f"unsupported Playwright test status: {status!r}")
            results = test.get("results") or []
            if not isinstance(results, list) or len(results) != 1:
                raise ValueError(
                    "Playwright report must contain one non-retried result per test"
                )
            result = results[0]
            if not isinstance(result, dict) or result.get("retry") != 0:
                raise ValueError("Playwright report contains an invalid retry result")
            result_status = str(result.get("status") or "").strip()
            if result_status not in {
                "passed",
                "failed",
                "timedOut",
                "interrupted",
                "skipped",
            }:
                raise ValueError(
                    f"unsupported Playwright result status: {result_status!r}"
                )
            if status == "expected" and (
                result_status != "passed"
                or spec.get("ok") is not True
                or (result.get("errors") or [])
            ):
                raise ValueError("Playwright expected result is not a clean pass")
            if status == "unexpected" and result_status == "passed":
                raise ValueError("Playwright unexpected result cannot be passed")
            if status == "skipped" and result_status != "skipped":
                raise ValueError("Playwright skipped status does not match its result")
            if test_id in observed_ids:
                raise ValueError(f"duplicate Playwright test id: {test_id}")
            observed_ids.add(test_id)
            observed_files.add(safe_file.as_posix())
            observed_statuses[status] += 1
            inventory.append(
                {
                    "id": test_id,
                    "title": title,
                    "file": safe_file.as_posix(),
                    "line": int(spec.get("line") or 0),
                    "column": int(spec.get("column") or 0),
                    "project_id": project_id,
                    "project_name": project_name,
                }
            )

    if len(inventory) != expected_test_count:
        raise ValueError(
            f"Playwright report enumerates {len(inventory)} tests, expected {expected_test_count}"
        )
    if expected_test_files is not None and observed_files != expected_test_files:
        raise ValueError(
            "Playwright report file set differs from the locked test manifest"
        )
    inventory.sort(key=lambda item: (item["file"], item["id"], item["project_id"]))
    inventory_sha256 = hashlib.sha256(
        json.dumps(
            inventory,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if inventory_sha256 != expected_inventory_sha256:
        raise ValueError("Playwright test inventory hash is not the locked inventory")

    stats = payload.get("stats") or {}
    if not isinstance(stats, dict):
        raise ValueError("Playwright report stats must be an object")
    expected_stats = {
        "expected": observed_statuses["expected"],
        "unexpected": observed_statuses["unexpected"],
        "skipped": observed_statuses["skipped"],
        "flaky": observed_statuses["flaky"],
    }
    if any(stats.get(name) != count for name, count in expected_stats.items()):
        raise ValueError("Playwright stats do not match enumerated test results")
    config = payload.get("config") or {}
    if not isinstance(config, dict):
        raise ValueError("Playwright report config must be an object")
    if expected_workers is not None and config.get("workers") != expected_workers:
        raise ValueError("Playwright report worker count differs from the invocation")
    if (
        expected_fully_parallel is not None
        and config.get("fullyParallel") is not expected_fully_parallel
    ):
        raise ValueError("Playwright parallel mode differs from the invocation")
    return {
        "test_count": len(inventory),
        "test_file_count": len(observed_files),
        "inventory_sha256": inventory_sha256,
        "status_counts": expected_stats,
    }


def _error_text(result: dict[str, Any]) -> str:
    errors = result.get("errors") or []
    chunks = []
    for error in errors:
        if isinstance(error, dict):
            chunks.append(str(error.get("message") or error.get("stack") or ""))
        elif error:
            chunks.append(str(error))
    if not chunks and result.get("error"):
        error = result["error"]
        chunks.append(str(error.get("message") if isinstance(error, dict) else error))
    return "\n".join(chunk for chunk in chunks if chunk).strip()


def failure_signature(error: str) -> str:
    locator = LOCATOR_PATTERN.search(error)
    if locator:
        normalized = re.sub(r"\d+", "#", locator.group(1).strip().lower())
        return "locator:" + normalized[:220]
    first_error = ERROR_PATTERN.search(error)
    if first_error:
        normalized = re.sub(r"\d+(?:\.\d+)?(?:ms|s)?", "#", first_error.group(1).strip().lower())
        return "error:" + normalized[:220]
    first_line = next((line.strip() for line in error.splitlines() if line.strip()), "unknown failure")
    return "other:" + re.sub(r"\d+", "#", first_line.lower())[:220]


def failure_classification(error: str) -> str:
    if INFRASTRUCTURE_PATTERN.search(error):
        return "evaluator_infrastructure"
    if LOCATOR_PATTERN.search(error) or ERROR_PATTERN.search(error):
        return "product_behavior"
    return "unclassified_contract_failure"


def parse_playwright_json(payload: dict[str, Any]) -> list[PlaywrightFailure]:
    failures: list[PlaywrightFailure] = []
    for suite in _walk_suites(payload.get("suites") or []):
        suite_file = str(suite.get("file") or "")
        for spec in suite.get("specs") or []:
            if not isinstance(spec, dict):
                continue
            title = str(spec.get("title") or "")
            test_id = str(spec.get("id") or title or suite_file)
            file_path = str(spec.get("file") or suite_file)
            requirement_match = REQ_ID_PATTERN.search(" ".join((title, file_path, test_id)))
            for test in spec.get("tests") or []:
                for result in test.get("results") or []:
                    status = str(result.get("status") or "").lower()
                    if status in {"passed", "skipped"}:
                        continue
                    error = _error_text(result) or f"Playwright status: {status or 'failed'}"
                    failures.append(
                        PlaywrightFailure(
                            test_id=test_id,
                            title=title,
                            file=file_path,
                            requirement_id=requirement_match.group(0) if requirement_match else None,
                            error=error,
                            signature=failure_signature(error),
                        )
                    )
    return failures


def repair_packets(
    failures: Iterable[PlaywrightFailure], impact: ChangeImpactGraph
) -> list[dict[str, Any]]:
    grouped: dict[str, list[PlaywrightFailure]] = {}
    for failure in failures:
        grouped.setdefault(failure.signature, []).append(failure)
    packets = []
    for signature, members in grouped.items():
        requirement_ids = sorted({member.requirement_id for member in members if member.requirement_id})
        classifications = {
            failure_classification(member.error) for member in members
        }
        classification = (
            "evaluator_infrastructure"
            if classifications == {"evaluator_infrastructure"}
            else "product_behavior"
            if "product_behavior" in classifications
            else "unclassified_contract_failure"
        )
        packets.append(
            {
                "signature": signature,
                "classification": classification,
                "repair_allowed": classification == "product_behavior",
                "failure_count": len(members),
                "requirement_ids": requirement_ids,
                "related_files": impact.files_for_requirements(requirement_ids),
                "tests": [
                    {
                        "test_id": member.test_id,
                        "title": member.title,
                        "file": member.file,
                    }
                    for member in members
                ],
                "representative_error": members[0].error[-4000:],
            }
        )
    return sorted(packets, key=lambda packet: (-packet["failure_count"], packet["signature"]))


def main() -> int:
    parser = argparse.ArgumentParser(description="Cluster public Playwright failures into minimal repair packets")
    parser.add_argument("report", type=Path, help="Playwright JSON reporter output")
    parser.add_argument("--impact", type=Path, required=True, help=".arc/change-impact.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.report.read_text(encoding="utf-8"))
    failures = parse_playwright_json(payload)
    packets = repair_packets(failures, ChangeImpactGraph(args.impact))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "version": 1,
                "failure_count": len(failures),
                "cluster_count": len(packets),
                "failures": [asdict(failure) for failure in failures],
                "repair_packets": packets,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
