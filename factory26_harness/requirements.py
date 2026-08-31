from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml


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
        lines = [f"[{self.req_id}] {self.name}".rstrip()]
        if self.description:
            lines.append(self.description)
        if self.dependencies:
            lines.append("Depends on: " + ", ".join(self.dependencies))
        for scenario in self.scenarios:
            title = str(scenario.get("name") or scenario.get("id") or "scenario")
            lines.append(f"Scenario: {title}")
            for step in scenario.get("steps") or []:
                if isinstance(step, dict):
                    keyword = str(step.get("keyword") or "").strip()
                    content = str(step.get("content") or step.get("text") or "").strip()
                    if content:
                        lines.append(f"  {keyword} {content}".rstrip())
                elif str(step).strip():
                    lines.append(f"  {str(step).strip()}")
        if self.visual_reference:
            lines.append("Visual references: " + ", ".join(self.visual_reference))
        return "\n".join(lines)


def _requirement_file(requirement_dir: Path) -> Path:
    if requirement_dir.is_file():
        return requirement_dir
    for name in ("requirements.yaml", "requirements.yml"):
        candidate = requirement_dir / name
        if candidate.is_file():
            return candidate
    candidates = sorted(requirement_dir.glob("*.yaml")) + sorted(requirement_dir.glob("*.yml"))
    if len(candidates) == 1:
        return candidates[0]
    raise FileNotFoundError(f"requirements.yaml not found in {requirement_dir}")


def load_requirement_tree(requirement_dir: Path) -> dict[str, Any]:
    requirement_file = _requirement_file(requirement_dir)
    payload = yaml.safe_load(requirement_file.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and not (payload.get("id") or payload.get("req_id")):
        for wrapper in ("root", "requirement", "requirements"):
            wrapped = payload.get(wrapper)
            if isinstance(wrapped, dict):
                payload = wrapped
                break
    if not isinstance(payload, dict) or not (payload.get("id") or payload.get("req_id")):
        raise ValueError(f"invalid requirement tree: {requirement_file}")
    return payload


def _walk(node: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield node
    for child in node.get("children") or []:
        if isinstance(child, dict):
            yield from _walk(child)


def _is_atomic(node: dict[str, Any]) -> bool:
    node_type = str(node.get("type") or "").upper()
    children = [child for child in node.get("children") or [] if isinstance(child, dict)]
    return node_type == "ATOMIC" or (not children and node_type != "FOLDER")


def flatten_atomic(tree: dict[str, Any]) -> list[RequirementNode]:
    nodes: list[RequirementNode] = []
    seen: set[str] = set()
    for raw in _walk(tree):
        if not _is_atomic(raw):
            continue
        req_id = str(raw.get("id") or raw.get("req_id") or "").strip()
        if not req_id or req_id in seen:
            continue
        seen.add(req_id)
        dependencies = tuple(
            str(value).strip() for value in raw.get("dependencies") or [] if str(value).strip()
        )
        scenarios = tuple(dict(item) for item in raw.get("scenarios") or [] if isinstance(item, dict))
        visual_reference = tuple(
            str(value).strip() for value in raw.get("visual_reference") or [] if str(value).strip()
        )
        nodes.append(
            RequirementNode(
                req_id=req_id,
                name=str(raw.get("name") or "").strip(),
                description=str(raw.get("description") or "").strip(),
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
            if dependency in by_id and dependency != node.req_id:
                indegree[node.req_id] += 1
                outgoing[dependency].append(node.req_id)
    ready = sorted((req_id for req_id, degree in indegree.items() if degree == 0), key=position.get)
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
        emitted = {node.req_id for node in ordered}
        ordered.extend(node for node in nodes if node.req_id not in emitted)
    return ordered


def batches(nodes: list[RequirementNode], size: int) -> list[list[RequirementNode]]:
    normalized = max(1, size)
    return [nodes[index : index + normalized] for index in range(0, len(nodes), normalized)]


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
                "dependencies": sorted({dep for node in group for dep in node.dependencies}),
            }
            for index, group in enumerate(groups, 1)
        ],
    }


def detect_domain(tree: dict[str, Any]) -> str:
    root_text = " ".join(
        str(tree.get(key) or "") for key in ("id", "name", "title", "description")
    ).lower()
    if any(token in root_text for token in ("spreadsheet", "workbook", "worksheet", "online sheet")):
        return "sheet"
    if any(token in root_text for token in ("github", "repository", "pull request", "code collaboration")):
        return "github"
    return "generic"
