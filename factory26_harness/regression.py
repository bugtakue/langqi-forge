"""Task-neutral replay memory for caller-promoted, successful browser probes.

The caller must only remember probes verified against the promoted source revision,
after the whole new batch succeeds. This module cannot infer that provenance from
steps, and neither collects probes automatically nor certifies requirements.
"""

from __future__ import annotations

import hashlib
import json
import time
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .browser_probe import probe_local_app, validate_steps
from .checks import CheckResult
from .isolation import app_source_manifest
from .trace import ProductionTrace


INTERACTION_ACTIONS = frozenset({"click", "fill", "press", "select", "check"})
MAX_SUMMARY_CHARS = 12_000
_RELATED_FILES = ("frontend/src/app.js", "backend/server.mjs")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _bounded(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit - 15] + "...[truncated]"


def _recipe(steps: list[dict]) -> list[dict]:
    validated = validate_steps(deepcopy(steps))
    # validate_steps coerces assertion values to strings. Such coercions must not
    # turn numbers/booleans/objects or whitespace into positive text evidence.
    for raw in steps:
        for key in ("expect_text", "expect_absent"):
            if any(not isinstance(text, str) or not text.strip()
                   for text in (raw.get(key) or [])):
                raise ValueError("assertions must contain nonblank, literal text strings")
    if not any(step["action"] in INTERACTION_ACTIONS for step in validated):
        raise ValueError("a capsule needs a click/fill/press/select/check interaction")
    if not any(step["expect_text"] for step in validated):
        raise ValueError("a capsule needs at least one positive expect_text assertion")
    return deepcopy(validated)


@dataclass(frozen=True)
class _Capsule:
    capsule_id: str
    requirement_ids: tuple[str, ...]
    steps: list[dict]
    origin_source_manifest_digest: str


def recheck_candidate_flows(
    root: Path, port: int, flows: list[list[dict]], trace: ProductionTrace,
) -> CheckResult:
    """Recheck pre-repair observations without publishing them as promoted memory."""
    started = time.monotonic()
    results: list[dict[str, Any]] = []
    source_digest = None
    error = ""
    try:
        if len(flows) > 5:  # WorkspaceTools' absolute per-batch launch cap.
            raise ValueError("too many candidate recipes")
        recipes = [_recipe(flow) for flow in flows]
        if recipes:
            source_digest = _digest(app_source_manifest(root))
        for recipe in recipes:
            item = {"recipe_hash": _digest(recipe), "passed": False, "error": ""}
            try:
                observed = probe_local_app(root, port, deepcopy(recipe))
                if not isinstance(observed, dict):
                    raise TypeError("probe must return a result dictionary")
                counts = [observed.get(key) for key in ("behavioral_checks", "behavioral_assertions")]
                counts = [n if type(n) is int and n > 0 else 0 for n in counts]
                item["error"] = RegressionMemory._probe_error(observed, *counts)
                item["passed"] = not item["error"]
            except Exception as exc:
                item["error"] = _bounded(f"{type(exc).__name__}: {exc}", 1000)
            results.append(item)
    except Exception as exc:
        error = _bounded(f"{type(exc).__name__}: {exc}", 1000)
    passed = not error and all(item["passed"] for item in results)
    status = "failed" if not passed else "passed" if flows else "no_coverage"
    trace.record(
        "candidate_behavior_recheck", status=status, source_manifest_digest=source_digest,
        recipe_count=len(flows), results=results, error=error,
        note="Pre-repair observed flows only; not promoted memory or requirement coverage",
    )
    return CheckResult(
        "candidate_behavior_recheck", passed,
        f"Pre-repair candidate flows: {status}; {sum(item['passed'] for item in results)}/{len(flows)}. "
        "A repair probe cannot substitute for these observations. Requirement coverage is not assessed.",
        _RELATED_FILES, round(time.monotonic() - started, 4),
    )


class RegressionMemory:
    def __init__(self, trace: ProductionTrace, maximum_capsules: int = 24) -> None:
        if type(maximum_capsules) is not int or maximum_capsules < 0:
            raise ValueError("maximum_capsules must be a nonnegative integer")
        self.trace = trace
        self.maximum_capsules = maximum_capsules
        self._capsules: dict[str, _Capsule] = {}
        self._rotation: list[str] = []
        self._history: list[dict[str, Any]] = []
        self._remember_history: list[dict[str, Any]] = []

    @property
    def history(self) -> list[dict[str, Any]]:
        """Detached, status-only evidence for every check, including no coverage."""
        return deepcopy(self._history)

    def _remember_result(
        self, status: str, capsule_id: str | None = None, *, error: str = ""
    ) -> bool:
        entry = {
            "status": status,
            "capsule_id": capsule_id,
            "capsule_count": len(self._capsules),
        }
        self._remember_history.append(entry)
        self.trace.record(
            "regression_check", phase="remember", **entry,
            error=_bounded(error, 1000),
        )
        return status == "stored"

    def remember(
        self, requirement_ids: list[str], steps: list[dict], source_manifest: dict[str, str]
    ) -> bool:
        """Store only an eligible recipe; the caller guarantees successful promotion.

        False means invalid, duplicate, or explicitly rejected for lack of capacity.
        Failed batches must never call this method, even for a successful subprobe.
        """
        try:
            recipe = _recipe(steps)
            if not isinstance(requirement_ids, list) or any(
                not isinstance(item, str) or not item.strip() for item in requirement_ids
            ):
                raise ValueError("requirement_ids must be a list of nonblank strings")
            if not isinstance(source_manifest, dict) or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in source_manifest.items()
            ):
                raise ValueError("source_manifest must map strings to strings")
            requirements = tuple(sorted(set(requirement_ids)))
            origin = _digest(deepcopy(source_manifest))
            capsule_id = _digest({
                "recipe": recipe,
                "requirement_ids": requirements,
                "origin_source_manifest_digest": origin,
            })
        except (TypeError, ValueError) as exc:
            return self._remember_result("rejected_invalid", error=str(exc))
        if capsule_id in self._capsules:
            return self._remember_result("duplicate", capsule_id)
        if len(self._capsules) >= self.maximum_capsules:
            return self._remember_result("rejected_capacity", capsule_id)
        self._capsules[capsule_id] = _Capsule(capsule_id, requirements, recipe, origin)
        self._rotation.append(capsule_id)
        # Keep the recoverable recipe in the sealed trace. Only the trace's
        # explicit safe-metadata projection may expose this event to stdout.
        self.trace.record(
            "regression_capsule_stored",
            capsule_id=capsule_id,
            requirement_ids=list(requirements),
            steps=deepcopy(recipe),
            origin_source_manifest_digest=origin,
        )
        return self._remember_result("stored", capsule_id)

    def _select(self, requirement_ids: tuple[str, ...], final: bool) -> list[str]:
        if final:
            return list(self._capsules)
        requested = set(requirement_ids)
        matching = [
            capsule_id for capsule_id in self._rotation
            if requested.intersection(self._capsules[capsule_id].requirement_ids)
        ]
        # At most one priority slot. The oldest unselected capsule always gets
        # the other slot, even when there are many intersecting requirements.
        selected = matching[:1]
        selected.extend(
            [capsule_id for capsule_id in self._rotation if capsule_id not in selected]
            [:2 - len(selected)]
        )
        self._rotation = [item for item in self._rotation if item not in selected] + selected
        return selected

    @staticmethod
    def _probe_error(result: dict, checks: int, assertions: int) -> str:
        reasons = []
        if result.get("ok") is not True:
            reasons.append("probe ok is not true")
        if checks == 0:
            reasons.append("behavioral_checks must be a positive integer")
        if assertions == 0:
            reasons.append("behavioral_assertions must be a positive integer")
        details = {
            key: result[key]
            for key in ("error", "assertion_failures", "page_errors", "blocked_external_hosts")
            if result.get(key)
        }
        if details:
            reasons.append(_canonical(details))
        return _bounded("; ".join(reasons), 1000)

    def _replay(self, root: Path, port: int, capsule: _Capsule) -> tuple[dict, str]:
        evidence = {
            "capsule_id": capsule.capsule_id,
            "origin_source_manifest_digest": capsule.origin_source_manifest_digest,
            "status": "failed",
            "behavioral_checks": 0,
            "behavioral_assertions": 0,
        }
        try:
            # Each invocation stages a fresh seed and browser context. Never
            # concatenate recipes or feed one probe's state into the next one.
            result = probe_local_app(root, port, deepcopy(capsule.steps))
            if not isinstance(result, dict):
                raise TypeError("probe must return a result dictionary")
            for key in ("behavioral_checks", "behavioral_assertions"):
                value = result.get(key)
                if type(value) is int and value > 0:
                    evidence[key] = value
            error = self._probe_error(
                result, evidence["behavioral_checks"], evidence["behavioral_assertions"]
            )
            if not error:
                evidence["status"] = "passed"
        except Exception as exc:
            error = _bounded(f"{type(exc).__name__}: {exc}", 1000)
        return evidence, error

    def _failure_detail(self, capsule_id: str, error: str) -> dict[str, str]:
        return {
            "capsule_id": capsule_id,
            "error": _bounded(error, 1000),
            "steps": _bounded(_canonical(self._capsules[capsule_id].steps), 4000),
        }

    def _finish(
        self, entry: dict, started: float, failures: list[dict], source_error: str = ""
    ) -> CheckResult:
        selected_count = len(entry["selected_ids"])
        failed_ids = [row["capsule_id"] for row in entry["results"] if row["status"] != "passed"]
        entry["failed_ids"] = failed_ids
        entry["status"] = (
            "no_coverage" if not selected_count else
            "failed" if failed_ids or source_error else "passed"
        )
        entry["source_status"] = (
            "failed" if source_error else "recorded" if selected_count else "not_read"
        )
        if entry["status"] == "no_coverage":
            summary = "No coverage: no regression capsules stored; no behavioral verification performed."
        elif entry["status"] == "passed":
            summary = (
                f"Replayed {selected_count} stored behavior capsule(s); "
                f"{len(entry['unselected_ids'])} unselected. Requirement coverage is not assessed."
            )
        else:
            summary = (
                f"Regression failed: {len(failed_ids)}/{selected_count} capsule(s) failed or not run. "
                "Repair the errors below and replay the stored steps on a fresh seed. "
                "Requirement coverage is not assessed."
            )
            if source_error:
                summary += "\nSource manifest error: " + _bounded(source_error, 1000)
            for failure in failures[:2]:
                summary += (
                    f"\nCapsule {failure['capsule_id']}: error={failure['error']}"
                    f"; steps={failure['steps']}"
                )
            if len(failures) > 2:
                summary += f"\n{len(failures) - 2} additional failures recorded in regression_check trace."
        self.trace.record(
            "regression_check", phase="completed", **deepcopy(entry),
            failure_details=failures, source_error=_bounded(source_error, 1000),
        )
        return CheckResult(
            name="behavior_regression", passed=entry["status"] != "failed",
            summary=_bounded(summary, MAX_SUMMARY_CHARS), related_files=_RELATED_FILES,
            duration_seconds=round(time.monotonic() - started, 4),
        )

    def check(
        self, root: Path, port: int, *, requirement_ids: tuple[str, ...] = (), final: bool = False
    ) -> CheckResult:
        """Replay up to two capsules, or all for final acceptance, without collecting.

        Call after successful build/startup checks. Source hashes are evidence of
        this replay, not a demand that later revisions equal the origin revision.
        """
        started = time.monotonic()
        selected = self._select(requirement_ids, final)
        entry: dict[str, Any] = {
            "check_id": len(self._history) + 1,
            "final": final,
            "requirement_ids": sorted(set(requirement_ids)),
            "capsule_count": len(self._capsules),
            "selected_ids": selected,
            "unselected_ids": [item for item in self._capsules if item not in selected],
            "status": "running",
            "source_manifest_digest": None,
            "results": [],
        }
        self._history.append(entry)
        self.trace.record("regression_check", phase="selected", **deepcopy(entry))
        if not selected:
            return self._finish(entry, started, [])
        try:
            entry["source_manifest_digest"] = _digest(app_source_manifest(root))
        except Exception as exc:
            error = _bounded(f"{type(exc).__name__}: {exc}", 1000)
            entry["results"] = [
                {"capsule_id": item, "status": "not_run", "behavioral_checks": 0,
                 "behavioral_assertions": 0} for item in selected
            ]
            return self._finish(
                entry, started, [self._failure_detail(item, error) for item in selected], error
            )
        failures = []
        for capsule_id in selected:
            evidence, error = self._replay(root, port, self._capsules[capsule_id])
            entry["results"].append(evidence)
            if error:
                failures.append(self._failure_detail(capsule_id, error))
        return self._finish(entry, started, failures)

    def summary(self) -> dict:
        """Return counts, identities and statuses, never recipes or page observations."""
        statuses = dict.fromkeys(self._capsules, "not_replayed")
        for entry in self._history:
            for result in entry["results"]:
                statuses[result["capsule_id"]] = result["status"]
        return {
            "capsule_count": len(self._capsules),
            "maximum_capsules": self.maximum_capsules,
            "capsule_ids": list(self._capsules),
            "capsule_statuses": statuses,
            "requirement_coverage": "not_assessed",
            "check_count": len(self._history),
            "failed_check_count": sum(item["status"] == "failed" for item in self._history),
            "last_check_status": self._history[-1]["status"] if self._history else "not_checked",
            "duplicate_count": sum(item["status"] == "duplicate" for item in self._remember_history),
            "rejected_invalid_count": sum(
                item["status"] == "rejected_invalid" for item in self._remember_history
            ),
            "rejected_capacity_count": sum(
                item["status"] == "rejected_capacity" for item in self._remember_history
            ),
            "history": self.history,
            "remember_history": deepcopy(self._remember_history),
        }
