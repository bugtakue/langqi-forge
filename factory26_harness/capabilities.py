from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .requirements import RequirementNode


@dataclass(frozen=True)
class CapabilityDefinition:
    capability_id: str
    domain: str
    version: str
    implemented: bool
    patterns: tuple[str, ...]
    description: str
    implementation_files: tuple[str, ...]
    validation_tests: tuple[str, ...]


@dataclass(frozen=True)
class RequirementCoverage:
    requirement_id: str
    capabilities: tuple[str, ...]
    matched_patterns: tuple[str, ...]
    implemented: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CoverageAnalysis:
    domain: str
    required_capabilities: tuple[str, ...]
    implemented_capabilities: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    covered_requirement_ids: tuple[str, ...]
    uncovered_requirement_ids: tuple[str, ...]
    requirements: tuple[RequirementCoverage, ...]

    @property
    def kernel_eligible(self) -> bool:
        return self.domain in CAPABILITY_CATALOG and not self.uncovered_requirement_ids

    def as_dict(self) -> dict[str, Any]:
        definitions = {
            item.capability_id: item
            for item in CAPABILITY_CATALOG.get(self.domain, ())
            if item.capability_id in self.required_capabilities
        }
        return {
            "version": 2,
            "domain": self.domain,
            "kernel_eligible": self.kernel_eligible,
            "required_capabilities": list(self.required_capabilities),
            "implemented_capabilities": list(self.implemented_capabilities),
            "missing_capabilities": list(self.missing_capabilities),
            "covered_requirement_ids": list(self.covered_requirement_ids),
            "uncovered_requirement_ids": list(self.uncovered_requirement_ids),
            "capability_evidence": {
                capability_id: {
                    "version": definition.version,
                    "implemented": definition.implemented,
                    "description": definition.description,
                    "implementation_files": list(definition.implementation_files),
                    "validation_tests": list(definition.validation_tests),
                }
                for capability_id, definition in sorted(definitions.items())
            },
            "requirements": [item.as_dict() for item in self.requirements],
        }


def _capability(
    capability_id: str,
    domain: str,
    *,
    implemented: bool,
    patterns: tuple[str, ...],
    description: str,
    version: str = "1",
    implementation_files: tuple[str, ...] | None = None,
    validation_tests: tuple[str, ...] | None = None,
) -> CapabilityDefinition:
    default_files = (
        (
            "factory26_harness/templates/github/backend/server.mjs",
            "factory26_harness/templates/github/frontend/src/app.js",
        )
        if domain == "github"
        else (
            "factory26_harness/templates/sheet/backend/server.mjs",
            "factory26_harness/templates/sheet/frontend/src/app.js",
        )
    )
    default_tests = (
        ("public ARC GitHub 101-test suite",)
        if domain == "github"
        else ("public ARC Spreadsheet 102-test suite",)
    )
    return CapabilityDefinition(
        capability_id=capability_id,
        domain=domain,
        version=version,
        implemented=implemented,
        patterns=patterns,
        description=description,
        implementation_files=(
            default_files if implementation_files is None and implemented else implementation_files or ()
        ),
        validation_tests=(
            default_tests if validation_tests is None and implemented else validation_tests or ()
        ),
    )


CAPABILITIES: tuple[CapabilityDefinition, ...] = (
    _capability(
        "authentication",
        "github",
        implemented=True,
        patterns=(
            r"register|create (?:a )?(?:new )?(?:github )?account",
            r"sign[ -]?in|sign[ -]?out|forgot password|recover account|change (?:account )?password|authenticated session",
        ),
        description="Account lifecycle, credentials, recovery, and browser sessions.",
    ),
    _capability(
        "organization_permissions",
        "github",
        implemented=True,
        patterns=(
            r"(?:browse|create|manage) organization|organization (?:team|member|owner|repositories)",
            r"team member|team hierarchy|repository access|grant (?:a )?repository role|collaborator",
        ),
        description="Organizations, teams, memberships, roles, and repository grants.",
    ),
    _capability(
        "repository_lifecycle",
        "github",
        implemented=True,
        patterns=(
            r"(?:search|locate|list|browse|create|view|open|fork|clone|change|set|manage)\b.{0,48}\brepositor(?:y|ies)",
            r"repositor(?:y|ies)\b.{0,48}\b(?:search|creation|overview|fork|clone|visibility|namespace)",
        ),
        description="Repository search, creation, viewing, forking, clone URL, and visibility.",
    ),
    _capability(
        "code_and_branches",
        "github",
        implemented=True,
        patterns=(
            r"(?:browse|manage|create|list|switch|change)\b.{0,48}\b(?:repository files?|directories|branches?|default branch)",
            r"(?:view|inspect|search)\b.{0,48}\b(?:commit|revision|code)|changed files?|aggregate diff",
        ),
        description="Files, commits, diffs, code search, branches, and web editing.",
    ),
    _capability(
        "issues",
        "github",
        implemented=True,
        patterns=(
            r"(?:list|filter|view|create|edit|comment|assign|unassign|apply|close|reopen)\b.{0,48}\bissues?",
            r"issues?\b.{0,48}\b(?:discussion|title|description|participants?|labels?|milestone|close|reopen)",
        ),
        description="Issue lifecycle, discussion, metadata, and state transitions.",
    ),
    _capability(
        "pull_requests",
        "github",
        implemented=True,
        patterns=(
            r"(?:list|filter|compare|create|view|inspect|review|merge|close|reopen|request|remove)\b.{0,64}\bpull requests?",
            r"pull requests?\b.{0,64}\b(?:overview|commits?|changed files?|review|reviewers?|merge|draft)",
            r"review comments?|request changes|merge eligible|merge commit",
        ),
        description="Pull-request creation, review, diff comments, checks, and merge.",
    ),
    _capability(
        "branch_protection",
        "github",
        implemented=True,
        patterns=(r"branch protection|protect branches",),
        description="Branch protection with approval and status-check requirements.",
    ),
    _capability(
        "repository_relations",
        "github",
        implemented=True,
        patterns=(
            r"star(?:red|ring)? repositor|watch(?:ed|ing)? repositor",
            r"transfer (?:a )?repositor|delete (?:a )?repositor",
        ),
        description="Repository star, watch, transfer, and deletion relationships.",
        version="2",
        implementation_files=(
            "factory26_harness/templates/github/backend/enterprise.mjs",
            "factory26_harness/templates/github/frontend/src/enterprise.js",
            "factory26_harness/templates/github/frontend/src/app.js",
        ),
        validation_tests=(
            "tests/enterprise_kernel.test.mjs",
            "tests/enterprise_gui_checks.mjs",
            "public ARC GitHub 101-test suite",
        ),
    ),
    _capability(
        "issue_forms",
        "github",
        implemented=True,
        patterns=(r"issue forms?|yaml (?:structured )?forms?|dynamic form",),
        description="YAML-defined issue forms and schema-driven submissions.",
        version="2",
        implementation_files=(
            "factory26_harness/templates/github/backend/enterprise.mjs",
            "factory26_harness/templates/github/frontend/src/enterprise.js",
        ),
        validation_tests=(
            "tests/enterprise_kernel.test.mjs",
            "tests/enterprise_gui_checks.mjs",
        ),
    ),
    _capability(
        "actions_workflows",
        "github",
        implemented=True,
        patterns=(
            r"github actions?|actions workflow|workflow runs?|workflow dispatch",
            r"cron schedul|scheduled workflow|job dependency|runner|environment controls?",
        ),
        description="Directed workflow runs, jobs, schedules, environments, logs, and pull-request check provenance.",
        version="3",
        implementation_files=(
            "factory26_harness/templates/github/backend/enterprise.mjs",
            "factory26_harness/templates/github/frontend/src/enterprise.js",
        ),
        validation_tests=(
            "tests/enterprise_kernel.test.mjs",
            "tests/enterprise_gui_checks.mjs",
        ),
    ),
    _capability(
        "enterprise_identity",
        "github",
        implemented=True,
        patterns=(r"\bsso\b|saml|scim|identity provider|single sign[ -]?on",),
        description="Enterprise SSO, SAML, and SCIM identity lifecycle.",
        version="2",
        implementation_files=(
            "factory26_harness/templates/github/backend/enterprise.mjs",
            "factory26_harness/templates/github/frontend/src/enterprise.js",
        ),
        validation_tests=(
            "tests/enterprise_kernel.test.mjs",
            "tests/enterprise_gui_checks.mjs",
        ),
    ),
    _capability(
        "fine_grained_data_permissions",
        "github",
        implemented=True,
        patterns=(r"row[ -]?level|field[ -]?level|department data|fine[ -]?grained permission",),
        description="Hierarchical row-level and field-level data authorization.",
        version="2",
        implementation_files=(
            "factory26_harness/templates/github/backend/enterprise.mjs",
            "factory26_harness/templates/github/frontend/src/enterprise.js",
        ),
        validation_tests=(
            "tests/enterprise_kernel.test.mjs",
            "tests/enterprise_gui_checks.mjs",
        ),
    ),
    _capability(
        "audit_log",
        "github",
        implemented=True,
        patterns=(
            r"audit logs?|audit trail|compliance export",
            r"tamper[ -]?evident|non[ -]?repudiation|immutable history",
        ),
        description="Central append-only audit events, business-state roots, runtime blocking, query, and compliance export.",
        version="3",
        implementation_files=(
            "factory26_harness/templates/github/backend/enterprise.mjs",
            "factory26_harness/templates/github/frontend/src/enterprise.js",
        ),
        validation_tests=(
            "tests/enterprise_kernel.test.mjs",
            "tests/enterprise_gui_checks.mjs",
        ),
    ),
    _capability(
        "rulesets_codeowners",
        "github",
        implemented=True,
        patterns=(r"rulesets?|codeowners|code owners|separation of duties|bypass actors?",),
        description="Repository rulesets, CODEOWNERS, bypass policy, duty separation, direct-write blocking, and atomic merge enforcement.",
        version="3",
        implementation_files=(
            "factory26_harness/templates/github/backend/enterprise.mjs",
            "factory26_harness/templates/github/frontend/src/enterprise.js",
        ),
        validation_tests=(
            "tests/enterprise_kernel.test.mjs",
            "tests/enterprise_gui_checks.mjs",
        ),
    ),
    _capability(
        "workbook_lifecycle",
        "sheet",
        implemented=True,
        patterns=(
            r"(?:view|open|create|rename)\b.{0,40}\bworkbook",
            r"import csv|export (?:the current worksheet|.*) as csv",
        ),
        description="Workbook list, create, rename, import, export, and persistence.",
    ),
    _capability(
        "worksheet_structure",
        "sheet",
        implemented=True,
        patterns=(
            r"(?:add|rename|switch|delete)\b.{0,40}\bworksheets?",
            r"insert and delete rows|insert and delete columns",
        ),
        description="Worksheet tabs plus reversible row and column structure changes.",
    ),
    _capability(
        "cell_editing",
        "sheet",
        implemented=True,
        patterns=(
            r"(?:edit|select|paste|modify)\b.{0,40}\bcells?",
            r"formula bar|rectangular cell range|two-dimensional table data",
        ),
        description="Grid selection and cell editing through grid or formula bar.",
    ),
    _capability(
        "clipboard_and_history",
        "sheet",
        implemented=True,
        patterns=(r"copy|cut|paste|clipboard|undo|redo",),
        description="Clipboard interoperability and undo/redo history.",
    ),
    _capability(
        "formulas",
        "sheet",
        implemented=True,
        patterns=(r"formula|calculate|aggregate functions?|recalculate",),
        description="Formula parsing, recalculation, references, and error propagation.",
    ),
    _capability(
        "sorting_and_filtering",
        "sheet",
        implemented=True,
        patterns=(r"sort a data range|filter rows|sorting|filtering",),
        description="Stable sort and persistent filter rules.",
    ),
    _capability(
        "validation_and_references",
        "sheet",
        implemented=True,
        patterns=(r"validation|dropdown|numeric validation|reference",),
        description="Validation rules and reference-safe structural edits.",
    ),
    _capability(
        "pivot_tables",
        "sheet",
        implemented=True,
        patterns=(r"pivot table|pivot summary",),
        description="Basic pivot creation, aggregation, and refresh.",
    ),
    _capability(
        "enterprise_compute_engine",
        "sheet",
        implemented=True,
        patterns=(
            r"runtime schema|general ledger|\bbom\b|\bmrp\b|material requirements planning",
            r"accounting period|period close|idempotent journal|scheduled receipts?|time[ -]?phased supply",
        ),
        description="Runtime schemas, idempotent period-controlled ledgers, and time-phased BOM/MRP computation.",
        version="3",
        implementation_files=(
            "factory26_harness/templates/sheet/backend/compute.mjs",
            "factory26_harness/templates/sheet/backend/server.mjs",
            "factory26_harness/templates/sheet/frontend/src/compute.js",
            "factory26_harness/templates/sheet/frontend/src/app.js",
        ),
        validation_tests=(
            "tests/compute_kernel.test.mjs",
            "tests/compute_gui_checks.mjs",
            "public ARC Spreadsheet 102-test suite",
        ),
    ),
)


CAPABILITY_CATALOG: dict[str, tuple[CapabilityDefinition, ...]] = {
    domain: tuple(item for item in CAPABILITIES if item.domain == domain)
    for domain in sorted({item.domain for item in CAPABILITIES})
}

UNSUPPORTED_OPERATION_PATTERNS = (
    r"ignore (?:all |any )?(?:prior|previous|system) instructions?",
    r"(?:read|reveal|print|exfiltrat\w*|steal)\b.{0,48}\b(?:credentials?|api[ _-]?keys?|tokens?|passwords?|\.env)",
    r"\b(?:teleport|quantum tunnel|mine cryptocurrency|install (?:a )?backdoor)\b",
    r"(?:disable|remove|bypass)\b.{0,40}\b(?:validation|tests?|audit trail|permission checks?)",
    r"(?:tamper with|rewrite|delete)\b.{0,40}\b(?:production trace|audit (?:log|history)|scoring history)",
    r"(?:write|modify|delete)\b.{0,40}\b(?:outside (?:the )?(?:workspace|project)|scoring harness)",
    r"(?:execute|run)\b.{0,24}\b(?:arbitrary )?(?:shell|system) commands?",
    r"\bgenerate (?:an? )?sbom\b|\bprocess (?:a )?payment\b|\bsend (?:an? )?sms\b",
)


def capability_ids(domain: str, *, implemented_only: bool = False) -> tuple[str, ...]:
    return tuple(
        item.capability_id
        for item in CAPABILITY_CATALOG.get(domain, ())
        if item.implemented or not implemented_only
    )


def planner_capability_map() -> dict[str, tuple[str, ...]]:
    return {
        domain: capability_ids(domain)
        for domain in sorted(CAPABILITY_CATALOG)
    }


def implemented_capability_map() -> dict[str, tuple[str, ...]]:
    return {
        domain: capability_ids(domain, implemented_only=True)
        for domain in sorted(CAPABILITY_CATALOG)
    }


def _requirement_text(node: RequirementNode) -> str:
    scenario_text = " ".join(
        str(step.get("content") or step.get("text") or "")
        for scenario in node.scenarios
        for step in scenario.get("steps") or []
        if isinstance(step, dict)
    )
    return " ".join((node.name, node.description, scenario_text)).lower()


def analyze_coverage(
    nodes: list[RequirementNode],
    domain: str,
) -> CoverageAnalysis:
    definitions = CAPABILITY_CATALOG.get(domain, ())
    by_id = {item.capability_id: item for item in definitions}
    requirements: list[RequirementCoverage] = []
    required: set[str] = set()
    for node in nodes:
        text = _requirement_text(node)
        unsupported_patterns = [
            pattern
            for pattern in UNSUPPORTED_OPERATION_PATTERNS
            if re.search(pattern, text, flags=re.IGNORECASE)
        ]
        matched_capabilities: list[str] = []
        matched_patterns: list[str] = []
        for definition in definitions:
            evidence = [
                pattern
                for pattern in definition.patterns
                if re.search(pattern, text, flags=re.IGNORECASE)
            ]
            if evidence:
                matched_capabilities.append(definition.capability_id)
                matched_patterns.extend(evidence)
        implemented = (
            not unsupported_patterns
            and bool(matched_capabilities)
            and all(
                by_id[capability].implemented for capability in matched_capabilities
            )
        )
        matched_patterns.extend(
            f"unsupported:{pattern}" for pattern in unsupported_patterns
        )
        required.update(matched_capabilities)
        requirements.append(
            RequirementCoverage(
                requirement_id=node.req_id,
                capabilities=tuple(matched_capabilities),
                matched_patterns=tuple(matched_patterns),
                implemented=implemented,
            )
        )
    missing = {
        capability
        for capability in required
        if not by_id[capability].implemented
    }
    covered_ids = tuple(
        item.requirement_id for item in requirements if item.implemented
    )
    uncovered_ids = tuple(
        item.requirement_id for item in requirements if not item.implemented
    )
    return CoverageAnalysis(
        domain=domain,
        required_capabilities=tuple(sorted(required)),
        implemented_capabilities=tuple(
            sorted(capability for capability in required if capability not in missing)
        ),
        missing_capabilities=tuple(sorted(missing)),
        covered_requirement_ids=covered_ids,
        uncovered_requirement_ids=uncovered_ids,
        requirements=tuple(requirements),
    )
