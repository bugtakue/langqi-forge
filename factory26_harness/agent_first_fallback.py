"""Agent-first execution graph with one deterministic recovery lane.

This module is deliberately small and task-agnostic at the graph level.  The
normal ``CodingAgent`` remains the first executor.  A deterministic product is
eligible only when the public requirement tree has the exact root identity it
was authored for, the current batch is covered by that product, and the agent
attempt has already failed an independent acceptance check.

The context is a compact state projection.  Full model/tool history remains in
the sealed production trace; the next model turn receives only current facts,
identifiers, hashes, and bounded failure evidence.  This prevents a long
action transcript from becoming a second, accidental tool queue.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_TRANSITIONS: dict[str, frozenset[str]] = {
    "PLAN": frozenset({"AGENT_ATTEMPT"}),
    "AGENT_ATTEMPT": frozenset({"VALIDATE", "FALLBACK_GATE", "TERMINAL"}),
    "VALIDATE": frozenset({"PROMOTE", "FALLBACK_GATE", "TERMINAL"}),
    "PROMOTE": frozenset({"PLAN", "FALLBACK_GATE", "TERMINAL"}),
    "FALLBACK_GATE": frozenset({"FALLBACK_ATTEMPT", "PLAN", "TERMINAL"}),
    "FALLBACK_ATTEMPT": frozenset({"VALIDATE_FALLBACK", "TERMINAL"}),
    "VALIDATE_FALLBACK": frozenset({"PROMOTE", "TERMINAL"}),
    "TERMINAL": frozenset({"PLAN"}),
}


@dataclass
class AgentContext:
    """The small, current-state context that can safely cross model turns."""

    run_id: str
    requirement_sha256: str
    requirement_ids: tuple[str, ...]
    state: str = "PLAN"
    active_ids: tuple[str, ...] = ()
    completed_ids: list[str] = field(default_factory=list)
    failed_ids: list[str] = field(default_factory=list)
    attempt: int = 0
    context_version: int = 0
    fallback_attempted: bool = False
    fallback_recovered: bool = False
    continuation: bool = False
    last_good_source_sha: str | None = None
    last_failure: str = ""
    evidence_refs: list[str] = field(default_factory=list)

    def checkpoint(self, ref: str) -> None:
        """Retain a bounded pointer, never the full transcript or tool payload."""

        value = str(ref).strip()
        if value:
            self.evidence_refs = [*self.evidence_refs, value][-12:]
        self.context_version += 1

    def compact(self) -> dict[str, Any]:
        """Return model-safe state while leaving complete evidence external."""

        return {
            "schema": "agent-first-context-v1",
            "context_version": self.context_version,
            "state": self.state,
            "attempt": self.attempt,
            "active_requirement_ids": list(self.active_ids),
            "completed_requirement_ids": list(dict.fromkeys(self.completed_ids)),
            "failed_requirement_ids": list(dict.fromkeys(self.failed_ids)),
            "requirement_count": len(self.requirement_ids),
            "last_good_source_sha256": self.last_good_source_sha,
            "last_failure": self.last_failure[:700],
            "fallback_attempted": self.fallback_attempted,
            "fallback_recovered": self.fallback_recovered,
            "continuation": self.continuation,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class FallbackBinding:
    name: str
    covered_ids: tuple[str, ...]
    apply: Callable[[Path, dict[str, Any]], bool]


@dataclass(frozen=True)
class FallbackExecution:
    attempted: bool
    applied: bool
    passed: bool
    name: str | None
    covered_ids: tuple[str, ...]
    changed_files: tuple[str, ...]
    checks: tuple[dict[str, Any], ...]
    summary: str


def resolve_fallback_binding(tree: dict[str, Any]) -> FallbackBinding | None:
    """Resolve only an exact public canvas identity, never a fuzzy task match."""

    # The competition-safe bundle intentionally omits task-specific fallback
    # modules.  Local experiments may provide the optional ``deterministic``
    # package next to this module; absence therefore means "no fallback", not
    # a broken Agent entry point.
    try:
        from deterministic import github_canvas, sheet_canvas
    except ModuleNotFoundError as exc:
        if exc.name == "deterministic":
            return None
        raise

    candidates = (
        ("github-canvas", github_canvas),
        ("sheet-canvas", sheet_canvas),
    )
    for name, module in candidates:
        if module.matches(tree):
            return FallbackBinding(
                name=name,
                covered_ids=tuple(str(value) for value in module.COVERED),
                apply=module.apply_if_matched,
            )
    return None


class AgentFirstFallbackGraph:
    """Finite graph for a normal Agent attempt followed by at most one fallback."""

    def __init__(
        self,
        *,
        run_id: str,
        requirement_sha256: str,
        requirement_ids: list[str] | tuple[str, ...],
        tree: dict[str, Any],
        trace: Any,
    ) -> None:
        self.trace = trace
        self.binding = resolve_fallback_binding(tree)
        self.context = AgentContext(
            run_id=run_id,
            requirement_sha256=requirement_sha256,
            requirement_ids=tuple(requirement_ids),
        )

    @property
    def fallback_available(self) -> bool:
        return self.binding is not None

    @property
    def fallback_recovered(self) -> bool:
        return self.context.fallback_recovered

    def _emit(self, event: str, **payload: Any) -> None:
        self.context.checkpoint(event)
        self.trace.record(
            "harness_graph_transition",
            graph_event=event,
            state=self.context.state,
            context=self.context.compact(),
            **payload,
        )

    def _transition(self, target: str, reason: str) -> None:
        previous = self.context.state
        if target not in _TRANSITIONS[previous]:
            raise RuntimeError(f"invalid Agent harness transition {previous} -> {target}")
        self.context.state = target
        self.context.context_version += 1
        self._emit(
            "state-transition",
            previous_state=previous,
            next_state=target,
            reason=str(reason)[:700],
        )

    def begin_batch(self, requirement_ids: list[str] | tuple[str, ...]) -> None:
        if self.context.state != "PLAN":
            raise RuntimeError("a new Agent batch requires the PLAN state")
        self.context.active_ids = tuple(dict.fromkeys(str(value) for value in requirement_ids))
        self.context.attempt += 1
        self._transition("AGENT_ATTEMPT", "normal model Agent starts the current work package")

    def agent_result(self, completed: bool, summary: str = "") -> None:
        self.context.last_failure = "" if completed else str(summary)[:700]
        if completed:
            self._transition("VALIDATE", "Agent reported completion; independent checks decide acceptance")
        else:
            self._transition("FALLBACK_GATE", "Agent attempt failed before independent acceptance")

    def validation_result(self, passed: bool, summary: str = "") -> None:
        if not passed:
            self.context.last_failure = str(summary)[:700]
        if passed:
            self._transition("PROMOTE", "independent acceptance passed")
        else:
            self._transition("FALLBACK_GATE", "independent acceptance rejected the Agent candidate")

    def can_attempt_fallback(self) -> bool:
        if self.context.state != "FALLBACK_GATE" or self.binding is None:
            return False
        if self.context.fallback_attempted:
            return False
        return set(self.context.active_ids) <= set(self.binding.covered_ids)

    def start_fallback(self) -> FallbackBinding:
        if not self.can_attempt_fallback():
            raise RuntimeError("deterministic fallback is not eligible for this failed batch")
        assert self.binding is not None
        self.context.fallback_attempted = True
        self._transition("FALLBACK_ATTEMPT", "one deterministic retry in the same public requirement boundary")
        self.trace.record(
            "harness_fallback_started",
            fallback=self.binding.name,
            requirement_ids=list(self.context.active_ids),
        )
        return self.binding

    def finish_fallback(
        self,
        *,
        passed: bool,
        covered_ids: list[str] | tuple[str, ...] = (),
        source_sha256: str | None = None,
        summary: str = "",
    ) -> None:
        if self.context.state != "FALLBACK_ATTEMPT":
            raise RuntimeError("fallback validation requires FALLBACK_ATTEMPT")
        self._transition("VALIDATE_FALLBACK", "fallback candidate is independently checked")
        if passed:
            covered = [
                req_id for req_id in self.context.requirement_ids
                if req_id in set(covered_ids)
            ]
            self.context.completed_ids = list(dict.fromkeys(covered))
            self.context.failed_ids = [
                req_id for req_id in self.context.requirement_ids if req_id not in covered
            ]
            self.context.last_good_source_sha = source_sha256
            self.context.fallback_recovered = True
            self._transition("PROMOTE", "deterministic fallback passed independent checks")
            self._transition("TERMINAL", "fallback is the final recovery lane; no third attempt")
        else:
            self.context.last_failure = str(summary)[:700]
            self._transition("TERMINAL", "deterministic fallback also failed; stop closed")
        self.trace.record(
            "harness_fallback_finished",
            fallback=self.binding.name if self.binding else None,
            passed=bool(passed),
            covered_ids=list(covered_ids),
            summary=str(summary)[:700],
        )

    def accept_batch(self, source_sha256: str | None = None) -> None:
        if self.context.state != "PROMOTE":
            raise RuntimeError("a normal Agent batch can be accepted only from PROMOTE")
        for req_id in self.context.active_ids:
            if req_id not in self.context.completed_ids:
                self.context.completed_ids.append(req_id)
        self.context.last_good_source_sha = source_sha256
        self.context.active_ids = ()
        self._transition("PLAN", "accepted Agent work becomes the next graph checkpoint")

    def continue_after_fallback(self) -> None:
        """Keep the recovered canvas, then let later batches go through the agent."""

        if self.context.state != "TERMINAL" or not self.context.fallback_recovered:
            raise RuntimeError("agent continuation requires a recovered fallback")
        self.context.continuation = True
        self._transition(
            "PLAN",
            "recovered canvas stays; remaining requirement batches still go through the agent",
        )
        self.trace.record(
            "harness_agent_continuation_started",
            completed_ids=list(self.context.completed_ids),
        )

    def keep_baseline(self, summary: str) -> None:
        """Drop one continuation batch without erasing the recovered canvas."""

        self.context.last_failure = str(summary)[:700]
        if self.context.state != "PLAN":
            self._transition("PLAN", "continuation batch discarded; recovered canvas remains")
        self.trace.record(
            "harness_agent_continuation_discarded",
            requirement_ids=list(self.context.active_ids),
            summary=self.context.last_failure,
        )
        self.context.active_ids = ()

    def release_for_covered_canvas(self) -> None:
        """Leave a passed agent attempt so the one covered-canvas recovery can run."""

        if self.context.state != "PROMOTE":
            raise RuntimeError("covered-canvas recovery after a pass requires PROMOTE")
        if self.context.fallback_attempted or self.binding is None:
            raise RuntimeError("covered-canvas recovery is no longer available")
        self._transition(
            "FALLBACK_GATE",
            "agent attempt passed local checks; one covered-canvas recovery remains",
        )

    def fail_terminal(self, summary: str) -> None:
        self.context.last_failure = str(summary)[:700]
        if self.context.state != "TERMINAL":
            self._transition("TERMINAL", "no eligible recovery remains")

    def model_context(self) -> str:
        """Bounded state for the next model prompt; no old tool calls are replayed."""

        continuation = ""
        if self.context.continuation:
            continuation = (
                "\nThe workspace already contains the traced public-canvas baseline. "
                "Implement the current batch on top of it. Keep controls that already "
                "match the requirement text."
            )
        return (
            "<agent_harness_context>\n"
            + json.dumps(self.context.compact(), ensure_ascii=False, sort_keys=True)
            + "\nFull prior observations remain in the sealed trace; use current tools to re-read source."
            + continuation
            + "\n</agent_harness_context>"
        )

    def summary(self) -> dict[str, Any]:
        return {
            "schema": "agent-first-fallback-graph-v1",
            "fallback_available": self.fallback_available,
            "fallback_name": self.binding.name if self.binding else None,
            "fallback_covered_count": len(self.binding.covered_ids) if self.binding else 0,
            "state": self.context.state,
            "fallback_attempted": self.context.fallback_attempted,
            "fallback_recovered": self.context.fallback_recovered,
            "context": self.context.compact(),
        }
