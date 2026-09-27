"""Requirement tree parsing, dependency ordering and work-unit grouping."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Atomic:
    id: str
    name: str
    description: str
    deps: list[str]
    scenarios: list[dict]
    ancestors: list[dict]  # [{id, name, description}] from root to parent
    parent_id: str

    def scenario_text(self) -> str:
        out = []
        for i, sc in enumerate(self.scenarios, 1):
            out.append(f"Scenario {i}: {sc.get('name', '')}")
            for step in sc.get("steps") or []:
                out.append(f"  {step.get('keyword', '')}: {clean(step.get('content', ''))}")
        return "\n".join(out)

    def render(self, with_scenarios: bool = True) -> str:
        parts = [f"### {self.id}: {self.name}", f"Depends on: {', '.join(self.deps) or 'none'}", "",
                 clean(self.description)]
        if with_scenarios and self.scenarios:
            parts += ["", "Acceptance scenarios (each scenario is one hidden browser test):", self.scenario_text()]
        return "\n".join(parts)

    def render_context(self) -> str:
        return "\n\n".join(f"[{a['id']} {a['name']}] {clean(a['description'])}" for a in self.ancestors if a.get("description"))


@dataclass
class Spec:
    root_name: str
    root_description: str
    atomics: list[Atomic]
    folders: list[dict] = field(default_factory=list)
    by_id: dict = field(default_factory=dict)

    def full_text(self, with_scenarios: bool = True) -> str:
        """Whole requirement tree as markdown, in dependency order under folder headings."""
        lines = [f"# {self.root_name}", clean(self.root_description), ""]
        seen_folders: set[str] = set()
        for a in self.atomics:
            for anc in a.ancestors[1:]:
                if anc["id"] not in seen_folders:
                    seen_folders.add(anc["id"])
                    lines += [f"## {anc['id']}: {anc['name']}", clean(anc.get("description", "")), ""]
            lines += [a.render(with_scenarios), ""]
        return "\n".join(lines)

    def outline(self) -> str:
        return "\n".join(f"- {a.id}: {a.name} (deps: {', '.join(a.deps) or 'none'}; {len(a.scenarios)} scenarios)"
                         for a in self.atomics)


def clean(text: str) -> str:
    text = str(text or "")
    text = re.sub(r"\n?\s*Screenshot reference:\s*\n?\s*!\[[^\]]*\]\(([^)]+)\)", r"\n(Reference screenshot: \1)", text)
    return text.strip()


def load_spec(requirements_dir: Path) -> Spec:
    path = Path(requirements_dir) / "requirements.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    atomics: list[Atomic] = []
    folders: list[dict] = []

    def walk(node: dict, ancestors: list[dict]) -> None:
        info = {"id": node.get("id"), "name": node.get("name", ""), "description": node.get("description", "")}
        kind = (node.get("type") or "").upper()
        children = node.get("children") or []
        if kind == "ATOMIC" or (not children and node.get("scenarios")):
            atomics.append(Atomic(
                id=str(node["id"]), name=node.get("name", ""), description=node.get("description", ""),
                deps=[str(d) for d in node.get("dependencies") or []], scenarios=node.get("scenarios") or [],
                ancestors=list(ancestors), parent_id=ancestors[-1]["id"] if ancestors else "",
            ))
            return
        folders.append({**info, "deps": [str(d) for d in node.get("dependencies") or []]})
        for child in children:
            walk(child, ancestors + [info])

    walk(data, [])
    by_id = {a.id: a for a in atomics}
    # Folder dependencies apply to all their atomics.
    folder_deps = {f["id"]: f["deps"] for f in folders}
    for a in atomics:
        extra = []
        for anc in a.ancestors:
            extra += folder_deps.get(anc["id"], [])
        a.deps = list(dict.fromkeys(a.deps + extra))
    ordered = topo_order(atomics)
    spec = Spec(root_name=data.get("name", ""), root_description=data.get("description", ""), atomics=ordered,
                folders=folders, by_id=by_id)
    return spec


def expand_dep(dep: str, atomics: list[Atomic]) -> list[str]:
    """A dependency may name a folder; expand it to the atomics beneath it."""
    ids = {a.id for a in atomics}
    if dep in ids:
        return [dep]
    return [a.id for a in atomics if any(anc["id"] == dep for anc in a.ancestors)]


def topo_order(atomics: list[Atomic]) -> list[Atomic]:
    by_id = {a.id: a for a in atomics}
    index = {a.id: i for i, a in enumerate(atomics)}
    deps = {a.id: [d2 for d in a.deps for d2 in expand_dep(d, atomics) if d2 != a.id] for a in atomics}
    done: list[str] = []
    state: dict[str, int] = {}

    def visit(aid: str) -> None:
        if state.get(aid) == 2:
            return
        if state.get(aid) == 1:
            return  # cycle: ignore back edge
        state[aid] = 1
        for d in sorted(deps.get(aid, []), key=lambda x: index.get(x, 0)):
            if d in by_id:
                visit(d)
        state[aid] = 2
        done.append(aid)

    for a in atomics:
        visit(a.id)
    return [by_id[i] for i in done]


def group_units(spec: Spec, max_atomics: int = 3, max_scenarios: int = 9) -> list[list[Atomic]]:
    """Consecutive atomics sharing a parent folder form one unit (bounded size)."""
    units: list[list[Atomic]] = []
    for a in spec.atomics:
        if units:
            cur = units[-1]
            if (cur[0].parent_id == a.parent_id and len(cur) < max_atomics
                    and sum(len(x.scenarios) for x in cur) + len(a.scenarios) <= max_scenarios):
                cur.append(a)
                continue
        units.append([a])
    return units
