from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


MAX_REQUIREMENT_BYTES = max(
    1, int(os.environ.get("FACTORY26_MAX_REQUIREMENT_BYTES", "5000000"))
)
MAX_TREE_NODES = max(1, int(os.environ.get("FACTORY26_MAX_REQUIREMENT_NODES", "10000")))
MAX_TREE_DEPTH = max(1, int(os.environ.get("FACTORY26_MAX_REQUIREMENT_DEPTH", "64")))
MAX_TASK_OUTLINE_CHARS = 8_000
MAX_FOLDER_ORDERING_EDGES = 100_000
INLINE_ATOMIC_FIELDS = frozenset({
    "id", "req_id", "type", "name", "description", "dependencies",
    "scenarios", "visual_reference", "children",
})
INLINE_SCENARIO_FIELDS = frozenset({"id", "name", "steps"})
INLINE_STEP_FIELDS = frozenset({"keyword", "content", "text"})


def _bounded(value: Any, maximum: int) -> str:
    return str(value or "").strip()[:maximum]


def _list_field(node: dict[str, Any], field: str) -> list[Any]:
    value = node.get(field)
    if value is None:
        return []
    if not isinstance(value, list):
        node_id = str(node.get("id") or node.get("req_id") or "<unknown>")
        raise ValueError(f"requirement {node_id} field {field} must be an array")
    return value


def _safe_identifier(value: Any, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is missing")
    if len(text) > 160:
        raise ValueError(f"{label} exceeds 160 characters")
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        raise ValueError(f"{label} contains control characters")
    return text


@dataclass(frozen=True)
class RequirementNode:
    req_id: str
    name: str
    description: str
    dependencies: tuple[str, ...]
    scenarios: tuple[dict[str, Any], ...]
    visual_reference: tuple[str, ...]
    raw: dict[str, Any]
    full_context: tuple[str, ...] = ()
    context_abbreviated: bool = False

    def is_abbreviated(self) -> bool:
        # The compact prompt renders only the known schema. An organizer may
        # add acceptance or actor fields in a later task; force the pageable
        # original through the tool instead of silently omitting those rules.
        if self.raw.keys() - INLINE_ATOMIC_FIELDS:
            return True
        if (
            self.context_abbreviated
            or len(self.name) > 500
            or len(self.description) > 6000
            or len(self.dependencies) > 100
            or len(self.scenarios) > 100
            or len(self.visual_reference) > 50
        ):
            return True
        if (
            len(str(self.raw.get("name") or "").strip()) > 1000
            or len(str(self.raw.get("description") or "").strip()) > 20000
            or any(len(str(value).strip()) > 2000 for value in self.raw.get("visual_reference") or [])
        ):
            return True
        for scenario in self.scenarios:
            if scenario.keys() - INLINE_SCENARIO_FIELDS:
                return True
            if len(str(scenario.get("name") or scenario.get("id") or "scenario").strip()) > 500:
                return True
            steps = scenario.get("steps") or []
            if len(steps) > 100:
                return True
            for step in steps:
                if isinstance(step, dict):
                    if step.keys() - INLINE_STEP_FIELDS:
                        return True
                    if (
                        len(str(step.get("keyword") or "").strip()) > 40
                        or len(str(step.get("content") or step.get("text") or "").strip()) > 1200
                    ):
                        return True
                elif len(str(step).strip()) > 1200:
                    return True
        estimated_content = len(self.name) + len(self.description)
        for scenario in self.scenarios:
            estimated_content += len(str(scenario.get("name") or scenario.get("id") or "scenario"))
            for step in scenario.get("steps") or []:
                estimated_content += len(str(step.get("content") or step.get("text") or "")) if isinstance(step, dict) else len(str(step))
        return estimated_content > 7_000

    def full_spec_document(self) -> str:
        """Pageable original requirement data, never a hidden test or future batch."""

        atomic = (
            {key: value for key, value in self.raw.items() if key != "children"}
            if self.raw else {
                "id": self.req_id,
                "name": self.name,
                "description": self.description,
                "dependencies": list(self.dependencies),
                "scenarios": list(self.scenarios),
                "visual_reference": list(self.visual_reference),
            }
        )
        return json.dumps(
            {
                "requirement_id": self.req_id,
                "folder_context": list(self.full_context),
                "atomic_requirement": atomic,
                "effective_visual_references": list(self.visual_reference),
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

    def compact_spec(self) -> str:
        if self.is_abbreviated():
            description = self.description
            if len(description) > 1_800:
                description = (
                    description[:1_300]
                    + "\n[... bounded preview; original available through read_requirement_spec ...]\n"
                    + description[-500:]
                )
            lines = [f"[{self.req_id}] {_bounded(self.name, 500)}", description]
            if self.dependencies:
                lines.append("Depends on: " + ", ".join(self.dependencies[:8]))
            lines.append(f"Scenarios: {len(self.scenarios)} (read full details before editing)")
            for scenario in self.scenarios[:5]:
                lines.append("Scenario: " + _bounded(scenario.get("name") or scenario.get("id") or "scenario", 120))
            if self.visual_reference:
                lines.append("Visual references: " + ", ".join(
                    _bounded(value, 160) for value in self.visual_reference[:5]
                ))
            lines.append(
                "[ABBREVIATED: call read_requirement_spec for this requirement ID "
                "until complete=true before editing; omitted text may contain mandatory behavior.]"
            )
            return "\n".join(lines)
        lines = [f"[{_bounded(self.req_id, 160)}] {_bounded(self.name, 500)}".rstrip()]
        if self.description:
            lines.append(_bounded(self.description, 6000))
        if self.dependencies:
            lines.append("Depends on: " + ", ".join(self.dependencies[:100]))
        for scenario in self.scenarios[:100]:
            title = _bounded(
                scenario.get("name") or scenario.get("id") or "scenario", 500
            )
            lines.append(f"Scenario: {title}")
            for step in (scenario.get("steps") or [])[:100]:
                if isinstance(step, dict):
                    keyword = _bounded(step.get("keyword"), 40)
                    content = _bounded(
                        step.get("content") or step.get("text"), 1200
                    )
                    if content:
                        lines.append(f"  {keyword} {content}".rstrip())
                elif str(step).strip():
                    lines.append(f"  {_bounded(step, 1200)}")
        if self.visual_reference:
            lines.append(
                "Visual references: " + ", ".join(self.visual_reference[:50])
            )
        return "\n".join(lines)


def _requirement_file(requirement_dir: Path) -> Path:
    if requirement_dir.is_file():
        return requirement_dir
    for name in ("requirements.yaml", "requirements.yml"):
        candidate = requirement_dir / name
        if candidate.is_file():
            return candidate
    candidates = sorted(requirement_dir.glob("*.yaml")) + sorted(
        requirement_dir.glob("*.yml")
    )
    if len(candidates) == 1:
        return candidates[0]
    raise FileNotFoundError(f"requirements.yaml not found in {requirement_dir}")


def load_requirement_tree(requirement_dir: Path) -> dict[str, Any]:
    requirement_file = _requirement_file(requirement_dir)
    encoded = requirement_file.read_bytes()
    if len(encoded) > MAX_REQUIREMENT_BYTES:
        raise ValueError(
            f"requirement file exceeds {MAX_REQUIREMENT_BYTES} byte safety limit"
        )
    payload = yaml.safe_load(encoded.decode("utf-8"))
    if isinstance(payload, dict) and not (payload.get("id") or payload.get("req_id")):
        for wrapper in ("root", "requirement", "requirements"):
            wrapped = payload.get(wrapper)
            if isinstance(wrapped, dict):
                payload = wrapped
                break
    if not isinstance(payload, dict) or not (
        payload.get("id") or payload.get("req_id")
    ):
        raise ValueError(f"invalid requirement tree: {requirement_file}")
    return payload


def requirement_source_sha256(requirement_dir: Path) -> str:
    return hashlib.sha256(_requirement_file(requirement_dir).read_bytes()).hexdigest()


def _walk(node: dict[str, Any]) -> Iterable[dict[str, Any]]:
    stack: list[tuple[dict[str, Any], int]] = [(node, 0)]
    seen_objects: set[int] = set()
    emitted = 0
    while stack:
        current, depth = stack.pop()
        if depth > MAX_TREE_DEPTH:
            raise ValueError(
                f"requirement tree exceeds depth safety limit {MAX_TREE_DEPTH}"
            )
        object_id = id(current)
        if object_id in seen_objects:
            raise ValueError("requirement tree contains a cyclic or aliased object")
        seen_objects.add(object_id)
        emitted += 1
        if emitted > MAX_TREE_NODES:
            raise ValueError(
                f"requirement tree exceeds node safety limit {MAX_TREE_NODES}"
            )
        yield current
        raw_children = _list_field(current, "children")
        if any(not isinstance(child, dict) for child in raw_children):
            raise ValueError("requirement children must contain objects only")
        children = [child for child in raw_children if isinstance(child, dict)]
        stack.extend((child, depth + 1) for child in reversed(children))


def _is_atomic(node: dict[str, Any]) -> bool:
    node_type = str(node.get("type") or "").upper()
    children = _list_field(node, "children")
    return node_type == "ATOMIC" or (not children and node_type != "FOLDER")


def flatten_atomic(tree: dict[str, Any]) -> list[RequirementNode]:
    nodes: list[RequirementNode] = []
    seen: set[str] = set()
    for raw in _walk(tree):
        if not _is_atomic(raw):
            continue
        req_id = _safe_identifier(
            raw.get("id") or raw.get("req_id"), label="atomic requirement id"
        )
        if req_id in seen:
            raise ValueError(f"duplicate atomic requirement id: {req_id}")
        seen.add(req_id)
        dependencies = tuple(
            _safe_identifier(value, label=f"dependency of {req_id}")
            for value in _list_field(raw, "dependencies")
        )
        if len(set(dependencies)) != len(dependencies):
            raise ValueError(f"requirement {req_id} contains duplicate dependencies")
        raw_scenarios = _list_field(raw, "scenarios")
        if any(not isinstance(item, dict) for item in raw_scenarios):
            raise ValueError(f"requirement {req_id} scenarios must contain objects only")
        scenarios = tuple(dict(item) for item in raw_scenarios)
        visual_reference = tuple(
            _bounded(value, 2000)
            for value in _list_field(raw, "visual_reference")
            if str(value).strip()
        )
        nodes.append(
            RequirementNode(
                req_id=req_id,
                name=_bounded(raw.get("name"), 1000),
                description=_bounded(raw.get("description"), 20000),
                dependencies=dependencies,
                scenarios=scenarios,
                visual_reference=visual_reference,
                raw=dict(raw),
            )
        )
    if not nodes:
        raise ValueError("no atomic requirement nodes found")
    return _stable_topological_order(nodes, _folder_ordering_dependencies(tree))


def _folder_ordering_dependencies(tree: dict[str, Any]) -> dict[str, set[str]]:
    """Expand folder edges for scheduling, without inventing hard failure edges."""

    raw_nodes = list(_walk(tree))
    by_id: dict[str, dict[str, Any]] = {}
    for raw in raw_nodes:
        identifier = _safe_identifier(
            raw.get("id") or raw.get("req_id"), label="requirement id"
        )
        if identifier in by_id:
            raise ValueError(f"duplicate requirement id: {identifier}")
        by_id[identifier] = raw

    descendants: dict[str, tuple[str, ...]] = {}
    for raw in reversed(raw_nodes):
        identifier = str(raw.get("id") or raw.get("req_id"))
        children = _list_field(raw, "children")
        if _is_atomic(raw):
            if children:
                raise ValueError(f"atomic requirement {identifier} has children")
            descendants[identifier] = (identifier,)
        else:
            descendants[identifier] = tuple(
                leaf
                for child in children
                for leaf in descendants[str(child.get("id") or child.get("req_id"))]
            )

    ordering: dict[str, set[str]] = {}
    edge_count = 0
    for raw in raw_nodes:
        if not _list_field(raw, "children"):
            continue
        folder_id = str(raw.get("id") or raw.get("req_id"))
        dependencies = tuple(
            _safe_identifier(value, label=f"dependency of {folder_id}")
            for value in _list_field(raw, "dependencies")
        )
        if len(set(dependencies)) != len(dependencies):
            raise ValueError(f"requirement {folder_id} contains duplicate dependencies")
        for dependency in dependencies:
            if dependency not in descendants:
                raise ValueError(
                    f"requirement {folder_id} has unknown dependency {dependency}"
                )
            for leaf in descendants[folder_id]:
                prerequisites = ordering.setdefault(leaf, set())
                for prior in descendants[dependency]:
                    if prior == leaf:
                        raise ValueError("requirement dependency graph contains a cycle")
                    if prior not in prerequisites:
                        prerequisites.add(prior)
                        edge_count += 1
                        if edge_count > MAX_FOLDER_ORDERING_EDGES:
                            raise ValueError(
                                "folder dependency graph exceeds ordering edge safety limit"
                            )
    return ordering


def _stable_topological_order(
    nodes: list[RequirementNode],
    folder_ordering: dict[str, set[str]] | None = None,
) -> list[RequirementNode]:
    by_id = {node.req_id: node for node in nodes}
    position = {node.req_id: index for index, node in enumerate(nodes)}
    indegree = {node.req_id: 0 for node in nodes}
    outgoing: dict[str, list[str]] = {node.req_id: [] for node in nodes}
    for node in nodes:
        dependencies = set(node.dependencies) | (folder_ordering or {}).get(node.req_id, set())
        for dependency in sorted(dependencies, key=lambda value: position.get(value, len(nodes))):
            if dependency == node.req_id:
                raise ValueError(f"requirement cannot depend on itself: {node.req_id}")
            if dependency not in by_id:
                raise ValueError(
                    f"requirement {node.req_id} has unknown dependency {dependency}"
                )
            indegree[node.req_id] += 1
            outgoing[dependency].append(node.req_id)
    ready = sorted(
        (req_id for req_id, degree in indegree.items() if degree == 0), key=position.get
    )
    ordered: list[RequirementNode] = []
    while ready:
        req_id = ready.pop(0)
        ordered.append(by_id[req_id])
        for target in sorted(outgoing[req_id], key=position.get):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort(key=position.get)
    if len(ordered) != len(nodes):
        unresolved = sorted(
            node.req_id for node in nodes if node.req_id not in {item.req_id for item in ordered}
        )
        raise ValueError(
            "requirement dependency graph contains a cycle: " + ", ".join(unresolved)
        )
    return ordered


def batches(nodes: list[RequirementNode], size: int) -> list[list[RequirementNode]]:
    normalized = max(1, size)
    return [
        nodes[index : index + normalized] for index in range(0, len(nodes), normalized)
    ]


def task_outline(tree: dict[str, Any], nodes: list[RequirementNode]) -> str:
    """Bounded whole-task index for architecture; not an implementation spec."""

    entries: list[dict[str, Any]] = []
    root_name = _bounded(tree.get("name"), 160)
    for node in nodes:
        entry = {
            "id": node.req_id,
            "name": node.name[:140],
            "dependencies": list(node.dependencies[:12]),
        }
        candidate = entries + [entry]
        outline = json.dumps(
            {
                "root_name": root_name,
                "total_requirements": len(nodes),
                "listed_requirements": len(candidate),
                "requirements": candidate,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).replace("<", "\\u003c")
        if len(outline) > MAX_TASK_OUTLINE_CHARS:
            break
        entries.append(entry)
    return json.dumps(
        {
            "root_name": root_name,
            "total_requirements": len(nodes),
            "listed_requirements": len(entries),
            "requirements": entries,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("<", "\\u003c")


def plan_payload(nodes: list[RequirementNode], batch_size: int) -> dict[str, Any]:
    groups = batches(nodes, batch_size)
    return {
        "version": 1,
        "strategy": "deterministic-foundation-then-small-batches",
        "requirement_count": len(nodes),
        "batch_size": max(1, batch_size),
        "batches": [
            {
                "index": index,
                "requirement_ids": [node.req_id for node in group],
                "dependencies": sorted(
                    {dep for node in group for dep in node.dependencies}
                ),
            }
            for index, group in enumerate(groups, 1)
        ],
    }
