from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .impact import ChangeImpactGraph


REQ_ID_PATTERN = re.compile(r"\bREQ-[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*\b")
LOCATOR_PATTERN = re.compile(r"(?:Locator:|waiting for)\s*([^\n]+)", re.IGNORECASE)
ERROR_PATTERN = re.compile(r"(?:Error:|AssertionError:)\s*([^\n]+)", re.IGNORECASE)


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
        packets.append(
            {
                "signature": signature,
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
