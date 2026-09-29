"""Four-layer contract for one Factory26 run.

graph schedules atomic requirements.
context is the only model-visible task data for the current batch.
loop is the edit session inside one batch.
harness decides whether that session may be kept.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .requirements import (
    RequirementNode,
    batches,
    task_outline,
)

LAYERS = ("graph", "context", "loop", "harness")

CONTEXT_SECTIONS = (
    "task_outline",
    "current_batch_graph",
    "current_batch_specs",
    "prior_source_paths",
    "prior_batch_handoffs",
)

LOOP_STATES = (
    "read_or_edit",
    "quick_validation",
    "browser_probe",
    "acceptance_audit",
    "audit_pass",
    "stall",
)

HARNESS_GATES = (
    "scaffold_health",
    "isolated_candidate",
    "independent_checks",
    "bounded_repair",
    "browser_evidence",
    "dependency_block",
    "regression_replay",
    "promote_or_discard",
    "refuse_unedited_scaffold",
)

STALL_AFTER_NO_TOOL_TURNS = 3


@dataclass(frozen=True)
class RunPlan:
    """Schedule and budgets for one requirements tree. Holds no model output."""

    groups: tuple[tuple[RequirementNode, ...], ...]
    outline: str
    outline_index: dict[str, Any]
    max_turns: int
    repair_rounds: int

    @property
    def requirement_ids(self) -> tuple[str, ...]:
        return tuple(node.req_id for group in self.groups for node in group)

    def public_record(self) -> dict[str, Any]:
        listed = int(self.outline_index["listed_requirements"])
        total = len(self.requirement_ids)
        return {
            "layers": list(LAYERS),
            "graph": {
                "order": "stable_topological",
                "requirement_count": total,
                "batch_count": len(self.groups),
                "batches": [
                    [node.req_id for node in group] for group in self.groups
                ],
            },
            "context": {
                "sections": list(CONTEXT_SECTIONS),
                "outline_characters": len(self.outline),
                "listed_requirements": listed,
                "listed_folder_dependencies": int(
                    self.outline_index["listed_folder_dependencies"]
                ),
                "outline_covers_every_requirement": listed == total,
            },
            "loop": {
                "states": list(LOOP_STATES),
                "max_turns": self.max_turns,
                "stall_after_no_tool_turns": STALL_AFTER_NO_TOOL_TURNS,
                "acceptance_prefix": "AUDIT PASS",
            },
            "harness": {
                "gates": list(HARNESS_GATES),
                "repair_rounds": self.repair_rounds,
                "keeps_only_checked_edits": True,
            },
        }


def describe_run(
    tree: dict[str, Any],
    nodes: list[RequirementNode],
    *,
    batch_size: int,
    batch_spec_chars: int,
    max_turns: int,
    repair_rounds: int,
) -> RunPlan:
    """Cut one already-ordered requirement list into the run contract."""

    if max_turns < 2:
        raise ValueError("agent turn budget must keep room for validation")
    if repair_rounds < 0:
        raise ValueError("repair rounds cannot be negative")
    _require_dependency_order(nodes)
    groups = tuple(
        tuple(group)
        for group in batches(
            nodes,
            batch_size,
            max_spec_chars=batch_spec_chars,
            share_folder_context=True,
        )
    )
    if sum(len(group) for group in groups) != len(nodes):
        raise ValueError("batch schedule dropped or duplicated a requirement")
    outline = task_outline(tree, nodes)
    return RunPlan(
        groups=groups,
        outline=outline,
        outline_index=json.loads(outline),
        max_turns=max_turns,
        repair_rounds=repair_rounds,
    )


def current_batch_graph(
    nodes: list[RequirementNode],
    *,
    accepted_ids: Iterable[str] = (),
) -> str:
    """Edges for this batch only. Earlier acceptances stay identifiers, not transcripts."""

    batch_ids = [node.req_id for node in nodes]
    batch_set = set(batch_ids)
    accepted = [req_id for req_id in dict.fromkeys(accepted_ids) if req_id]
    payload = {
        "implement_only": batch_ids,
        "accepted_requirement_ids": accepted,
        "edges": [
            {
                "id": node.req_id,
                "dependencies_in_batch": [
                    dependency for dependency in node.dependencies if dependency in batch_set
                ],
                "dependencies_already_scheduled": [
                    dependency for dependency in node.dependencies if dependency not in batch_set
                ],
            }
            for node in nodes
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def loop_phase(
    *,
    edited: bool,
    validated: bool,
    probe_current: bool,
    audit_for_revision: bool,
    empty_turns: int,
) -> str:
    """Name the next useful step. Validation never counts as acceptance."""

    if empty_turns >= STALL_AFTER_NO_TOOL_TURNS:
        return "stall"
    if not edited:
        return "read_or_edit"
    if not validated:
        return "quick_validation"
    if not probe_current:
        return "browser_probe"
    if not audit_for_revision:
        return "acceptance_audit"
    return "audit_pass"


def _require_dependency_order(nodes: list[RequirementNode]) -> None:
    seen: set[str] = set()
    for node in nodes:
        if node.req_id in seen:
            raise ValueError(f"duplicate requirement in schedule: {node.req_id}")
        late = [dependency for dependency in node.dependencies if dependency not in seen]
        if late:
            raise ValueError(
                f"requirement {node.req_id} is scheduled before "
                + ", ".join(late)
            )
        seen.add(node.req_id)
