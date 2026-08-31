from __future__ import annotations

import hashlib
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

    def compact_spec(self) -> str:
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
                    lines.append(f"  {str(step).strip()}")
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
    return _stable_topological_order(nodes)


def _stable_topological_order(nodes: list[RequirementNode]) -> list[RequirementNode]:
    by_id = {node.req_id: node for node in nodes}
    position = {node.req_id: index for index, node in enumerate(nodes)}
    indegree = {node.req_id: 0 for node in nodes}
    outgoing: dict[str, list[str]] = {node.req_id: [] for node in nodes}
    for node in nodes:
        for dependency in node.dependencies:
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


def detect_domain(tree: dict[str, Any]) -> str:
    root_text = " ".join(
        str(tree.get(key) or "") for key in ("id", "name", "title", "description")
    ).lower()
    if any(
        token in root_text
        for token in ("spreadsheet", "workbook", "worksheet", "online sheet")
    ):
        return "sheet"
    if any(
        token in root_text
        for token in ("github", "repository", "pull request", "code collaboration")
    ):
        return "github"
    return "generic"
