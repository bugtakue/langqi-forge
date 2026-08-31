from __future__ import annotations

import argparse
import html
import json
import math
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from .artifacts import (
    atomic_write_json,
    canonical_json,
    read_json_object,
    sha256_file,
    trace_rows,
    verify_run_envelope,
)
from .capability_memory import verify_capability_capsule
from .qualification import qualify


IMPORTANT_EVENTS = (
    "requirements_compiled",
    "model_request",
    "model_response",
    "agent_tool_call",
    "execution_route_selected",
    "deterministic_scaffold",
    "validation_result",
    "public_evaluation_completed",
    "counterexample_observed",
    "capability_capsule_forged",
    "human_intervention_checkpoint",
    "run_completed",
)


def _safe_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.exists():
        raise ValueError(f"judge report output already exists: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _write_text_atomic(path: Path, content: str) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _evaluation_summary(
    project: Path, envelope: dict[str, Any]
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    public_root = project / ".arc" / "public-eval"
    for binding in envelope.get("evaluations") or []:
        if not isinstance(binding, dict):
            raise ValueError("run envelope evaluation entry is invalid")
        label = str(binding.get("run_label") or "")
        feedback_path = public_root / f"{label}.feedback.json"
        feedback = read_json_object(feedback_path)
        stats = feedback.get("stats") or {}
        expected = int(stats.get("expected") or 0)
        unexpected = int(stats.get("unexpected") or 0)
        skipped = int(stats.get("skipped") or 0)
        flaky = int(stats.get("flaky") or 0)
        green = (
            feedback.get("exit_code") == 0
            and expected > 0
            and unexpected == 0
            and skipped == 0
            and flaky == 0
        )
        summaries.append(
            {
                "label": label,
                "profile": str(feedback.get("fixture_profile") or "unknown"),
                "expected": expected,
                "passed": expected
                if green
                else max(0, expected - unexpected - skipped),
                "unexpected": unexpected,
                "skipped": skipped,
                "flaky": flaky,
                "workers": int(feedback.get("workers") or 0),
                "duration_seconds": float(feedback.get("duration_seconds") or 0),
                "green": green,
                "raw_report_sha256": str(
                    feedback.get("playwright_report_sha256") or ""
                ),
            }
        )
    return sorted(summaries, key=lambda item: item["label"])


def domain_summary(project_dir: Path, domain: str) -> dict[str, Any]:
    project = project_dir.expanduser().resolve()
    envelope = verify_run_envelope(project)
    report = read_json_object(project / ".arc" / "harness-report.json")
    planner = read_json_object(project / ".arc" / "planner-contract.json")
    rows = trace_rows(project / ".arc" / "production-trace.jsonl")
    if report.get("detected_domain") != domain:
        raise ValueError(
            f"judge report expected {domain}, got {report.get('detected_domain')}"
        )
    events = Counter(str(row.get("event") or "unknown") for row in rows)
    capsule_path = project / ".arc" / "capability-capsule.json"
    capsule = (
        verify_capability_capsule(capsule_path) if capsule_path.is_file() else None
    )
    evaluations = _evaluation_summary(project, envelope)
    contract = (
        planner.get("contract") if isinstance(planner.get("contract"), dict) else {}
    )
    coverage = report.get("capability_coverage") or {}
    usage = report.get("model_usage") or {}
    gateway = report.get("model_gateway") or {}
    return {
        "domain": domain,
        "run_id": str(report.get("run_id") or ""),
        "source_revision": str(
            (report.get("source_identity") or {}).get("revision") or ""
        ),
        "source_clean": (report.get("source_identity") or {}).get("worktree_clean"),
        "dry_run": bool(report.get("dry_run")),
        "route": str(report.get("execution_route") or ""),
        "planner_status": str(report.get("planner_status") or ""),
        "requirements": int(report.get("requirement_count") or 0),
        "duration_seconds": float(report.get("duration_seconds") or 0),
        "planner_iterations": int(report.get("planner_iterations") or 0),
        "coding_iterations": int(report.get("coding_agent_iterations") or 0),
        "manual_interventions": int(report.get("manual_interventions") or 0),
        "local_checks_green": bool(report.get("all_local_checks_passed")),
        "model": str(gateway.get("model") or "not invoked"),
        "gateway": str(gateway.get("provenance") or "offline"),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "http_attempts": int(usage.get("http_attempt_count") or 0),
        "capabilities": list(coverage.get("required_capabilities") or []),
        "uncovered": list(coverage.get("uncovered_requirement_ids") or []),
        "risks": list(contract.get("risks") or []),
        "validation_focus": list(contract.get("validation_focus") or []),
        "evaluations": evaluations,
        "capsule": (
            {
                "id": str(capsule.get("capsule_id") or ""),
                "profiles": list(
                    (capsule.get("promotion_gate") or {}).get("observed_profiles") or []
                ),
                "skips_revalidation": bool(
                    (capsule.get("reuse_policy") or {}).get("skips_revalidation")
                ),
            }
            if capsule
            else None
        ),
        "trace": {
            "rows": len(rows),
            "head": str(rows[-1].get("hash") or "GENESIS") if rows else "GENESIS",
            "important_events": {
                event: events[event] for event in IMPORTANT_EVENTS if events[event]
            },
        },
        "claim_boundary": str(report.get("claim_boundary") or ""),
    }


def _qualification_summary(
    qualification_path: Path,
    github_project: Path,
    sheet_project: Path,
) -> dict[str, Any]:
    resolved = qualification_path.expanduser().resolve()
    payload = read_json_object(resolved)
    if (
        payload.get("version") != 2
        or payload.get("gate") != "factory26-public-qualification-v2"
        or not isinstance(payload.get("passed"), bool)
    ):
        raise ValueError("judge report qualification uses an unsupported gate")
    model_policy = payload.get("model_policy")
    thresholds = payload.get("thresholds")
    evidence = payload.get("evidence")
    if not all(
        isinstance(value, dict) for value in (model_policy, thresholds, evidence)
    ):
        raise ValueError("judge report qualification is incomplete")

    allowed_value = model_policy.get("allowed_models")
    if allowed_value is None:
        allowed_models = None
    elif (
        isinstance(allowed_value, list)
        and allowed_value
        and all(isinstance(item, str) and item.strip() for item in allowed_value)
    ):
        allowed_models = tuple(allowed_value)
    else:
        raise ValueError("judge report qualification model allowlist is malformed")
    gateway_host = model_policy.get("required_gateway_host")
    gateway_provenance = model_policy.get("required_gateway_provenance")
    if gateway_host is not None and (
        not isinstance(gateway_host, str) or not gateway_host.strip()
    ):
        raise ValueError("judge report qualification gateway host is malformed")
    if gateway_provenance is not None and (
        not isinstance(gateway_provenance, str) or not gateway_provenance.strip()
    ):
        raise ValueError("judge report qualification provenance is malformed")
    try:
        github_max = float(thresholds["github_max_seconds"])
        sheet_max = float(thresholds["sheet_max_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("judge report qualification thresholds are malformed") from exc
    if not all(math.isfinite(value) and value > 0 for value in (github_max, sheet_max)):
        raise ValueError("judge report qualification thresholds must be positive")

    recomputed = qualify(
        github_project,
        sheet_project,
        github_max_seconds=github_max,
        sheet_max_seconds=sheet_max,
        allowed_models=allowed_models,
        expected_gateway_host=gateway_host,
        expected_gateway_provenance=gateway_provenance,
    )
    if recomputed.get("passed") is not payload.get("passed") or canonical_json(
        recomputed.get("evidence")
    ) != canonical_json(evidence):
        raise ValueError(
            "judge report qualification cannot be reproduced from these projects"
        )
    return {
        "supplied": True,
        "passed": payload["passed"],
        "path": resolved.name,
        "sha256": sha256_file(resolved),
    }


def build_report_data(
    github_project: Path,
    sheet_project: Path,
    qualification_path: Path | None = None,
) -> dict[str, Any]:
    domains = [
        domain_summary(github_project, "github"),
        domain_summary(sheet_project, "sheet"),
    ]
    qualification = (
        _qualification_summary(
            qualification_path,
            github_project,
            sheet_project,
        )
        if qualification_path
        else None
    )
    evaluations = [item for domain in domains for item in domain["evaluations"]]
    return {
        "version": 1,
        "title": "Langqi Forge / 琅岐铸造",
        "qualification": qualification
        if qualification is not None
        else {"supplied": False, "passed": False, "path": None, "sha256": None},
        "domains": domains,
        "totals": {
            "requirements": sum(domain["requirements"] for domain in domains),
            "expected_tests": sum(item["expected"] for item in evaluations),
            "passed_tests": sum(item["passed"] for item in evaluations),
            "all_evaluations_green": bool(evaluations)
            and all(item["green"] for item in evaluations),
            "manual_interventions": sum(
                domain["manual_interventions"] for domain in domains
            ),
            "prompt_tokens": sum(domain["prompt_tokens"] for domain in domains),
            "completion_tokens": sum(domain["completion_tokens"] for domain in domains),
            "dry_run": any(domain["dry_run"] for domain in domains),
        },
        "claim_boundary": (
            "This view is derived from sealed local artifacts. Public GUI success does not "
            "guarantee hidden tests, Top 20, or an award."
        ),
    }


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _short_hash(value: str) -> str:
    return value[:12] + "…" if len(value) > 12 else value


def _domain_card(domain: dict[str, Any]) -> str:
    evaluations = "".join(
        "<tr>"
        f"<td data-label=\"Run\"><span class=\"run-name\"><strong>{_escape(item['label'])}</strong>"
        f"<small>{_escape(item['profile'])}</small></span></td>"
        f"<td data-label=\"Score\">{item['passed']} / {item['expected']}</td>"
        f"<td data-label=\"Workers\">{item['workers']}</td>"
        f"<td data-label=\"Wall\">{item['duration_seconds']:.3f}s</td>"
        f"<td data-label=\"Gate\"><span class=\"status {'ok' if item['green'] else 'bad'}\">"
        f"{'GREEN' if item['green'] else 'FAILED'}</span></td>"
        "</tr>"
        for item in domain["evaluations"]
    )
    capabilities = "".join(
        f"<li>{_escape(capability)}</li>" for capability in domain["capabilities"]
    )
    events = "".join(
        f"<li><span>{_escape(event)}</span><strong>{count}</strong></li>"
        for event, count in domain["trace"]["important_events"].items()
    )
    capsule = domain.get("capsule")
    capsule_text = (
        f"{_short_hash(capsule['id'])} · profiles: {', '.join(capsule['profiles'])} · "
        f"revalidation skipped: {str(capsule['skips_revalidation']).lower()}"
        if capsule
        else "Not forged: required profiles are not all green or evidence is incomplete."
    )
    evaluations_green = bool(domain["evaluations"]) and all(
        item["green"] for item in domain["evaluations"]
    )
    model_run_green = (
        not domain["dry_run"]
        and domain["planner_status"] == "completed"
        and domain["local_checks_green"]
        and evaluations_green
    )
    if domain["dry_run"]:
        mode = "OFFLINE CANDIDATE"
        planner_status_class = "warn"
    elif model_run_green:
        mode = "MODEL-BACKED RUN"
        planner_status_class = "ok"
    else:
        mode = "MODEL RUN · GATE CLOSED"
        planner_status_class = "bad"
    return f"""
    <section class="domain-card">
      <div class="domain-head">
        <div><p class="eyebrow">{_escape(mode)}</p><h2>{_escape(domain['domain'].upper())}</h2></div>
        <span class="status {planner_status_class}">{_escape(domain['planner_status'])}</span>
      </div>
      <dl class="facts">
        <div><dt>Route</dt><dd>{_escape(domain['route'])}</dd></div>
        <div><dt>Requirements</dt><dd>{domain['requirements']}</dd></div>
        <div><dt>Generate</dt><dd>{domain['duration_seconds']:.3f}s</dd></div>
        <div><dt>Agent turns</dt><dd>{domain['planner_iterations']} planner / {domain['coding_iterations']} coding</dd></div>
        <div><dt>Model</dt><dd>{_escape(domain['model'])}</dd></div>
        <div><dt>Tokens</dt><dd>{domain['prompt_tokens']} in / {domain['completion_tokens']} out</dd></div>
      </dl>
      <h3>Locked GUI evaluations</h3>
      <div class="eval-table"><table><thead><tr><th>Run</th><th>Score</th><th>Workers</th><th>Wall</th><th>Gate</th></tr></thead>
      <tbody>{evaluations or '<tr><td colspan="5">No bound GUI evaluation</td></tr>'}</tbody></table></div>
      <div class="split">
        <div><h3>Closed-world capabilities</h3><ul class="chips">{capabilities}</ul></div>
        <div><h3>Sealed trace</h3><ul class="events">{events}</ul></div>
      </div>
      <div class="capsule"><strong>Capability capsule</strong><code>{_escape(capsule_text)}</code></div>
      <p class="hash">run {_escape(_short_hash(domain['run_id']))} · source {_escape(_short_hash(domain['source_revision']))} · trace {_escape(_short_hash(domain['trace']['head']))}</p>
    </section>
    """


def render_report(data: dict[str, Any]) -> str:
    totals = data["totals"]
    qualification = data["qualification"]
    if qualification["supplied"]:
        verdict = "QUALIFIED" if qualification["passed"] else "GATE CLOSED"
        verdict_class = "ok" if qualification["passed"] else "bad"
    elif totals["dry_run"]:
        verdict = "LOCAL CANDIDATE"
        verdict_class = "warn"
    else:
        verdict = "QUALIFICATION NOT SUPPLIED"
        verdict_class = "warn"
    cards = "".join(_domain_card(domain) for domain in data["domains"])
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">
<title>{_escape(data['title'])} · Judge Report</title>
<style>
:root{{--ink:#151918;--muted:#68716d;--line:#d9dfdc;--paper:#f5f7f5;--white:#fff;--green:#087f5b;--amber:#a35b00;--red:#b42318;--navy:#153b50}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font:14px/1.5 ui-sans-serif,system-ui,-apple-system,"PingFang SC",sans-serif;letter-spacing:0}}
main{{max-width:1240px;margin:auto;padding:32px 24px 64px}} header{{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;border-bottom:2px solid var(--ink);padding-bottom:20px}}
.brand{{font-size:14px;font-weight:800}} h1{{font-size:36px;line-height:1.05;margin:8px 0 0;letter-spacing:0}} .subtitle{{color:var(--muted);max-width:700px;margin:10px 0 0}}
.status{{display:inline-flex;align-items:center;border:1px solid currentColor;padding:4px 8px;font:700 11px/1 ui-monospace,monospace;white-space:nowrap}} .ok{{color:var(--green)}} .warn{{color:var(--amber)}} .bad{{color:var(--red)}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);background:var(--ink);color:white;margin:22px 0}} .metric{{padding:18px 20px;border-right:1px solid #3c4441}} .metric:last-child{{border:0}} .metric b{{font-size:28px;display:block}} .metric span{{color:#bcc6c2;font-size:12px}}
.pipeline{{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;background:var(--line);border:1px solid var(--line);margin:0 0 22px}} .pipeline div{{background:var(--white);padding:13px}} .pipeline b{{display:block;color:var(--navy)}} .pipeline span{{font-size:11px;color:var(--muted)}}
.domains{{display:grid;grid-template-columns:1fr 1fr;gap:18px}} .domain-card{{background:var(--white);border:1px solid var(--line);padding:20px;min-width:0}} .domain-head{{display:flex;justify-content:space-between;gap:16px;align-items:start}} .eyebrow{{font:700 10px/1 ui-monospace,monospace;color:var(--muted);margin:0 0 7px}} h2{{font-size:24px;margin:0}} h3{{font-size:12px;text-transform:uppercase;margin:20px 0 8px;color:var(--navy)}}
.facts{{display:grid;grid-template-columns:1fr 1fr;margin:18px 0 0;border-top:1px solid var(--line);border-left:1px solid var(--line)}} .facts div{{padding:10px;border-right:1px solid var(--line);border-bottom:1px solid var(--line);min-width:0}} dt{{font-size:10px;color:var(--muted);text-transform:uppercase}} dd{{margin:3px 0 0;font-weight:650;overflow-wrap:anywhere}}
table{{width:100%;border-collapse:collapse;font-size:12px}} th,td{{text-align:left;padding:8px;border-bottom:1px solid var(--line)}} th{{color:var(--muted);font-size:10px;text-transform:uppercase}} .run-name small{{display:block;color:var(--muted);font-size:10px}} .eval-table{{min-width:0;max-width:100%}}
.split{{display:grid;grid-template-columns:1fr 1fr;gap:16px}} ul{{list-style:none;padding:0;margin:0}} .chips{{display:flex;gap:5px;flex-wrap:wrap}} .chips li{{border:1px solid #b7c6bf;background:#f3faf6;padding:3px 6px;font:10px/1.3 ui-monospace,monospace}} .events li{{display:flex;justify-content:space-between;border-bottom:1px dotted var(--line);font:10px/1.7 ui-monospace,monospace;gap:8px}} .events span{{overflow-wrap:anywhere}}
.capsule{{margin-top:18px;padding:11px;background:#f0f4f6;border-left:3px solid var(--navy)}} .capsule strong{{display:block;font-size:11px}} code{{font-size:10px;overflow-wrap:anywhere}} .hash{{font:10px/1.5 ui-monospace,monospace;color:var(--muted);overflow-wrap:anywhere;margin:14px 0 0}}
.boundary{{margin-top:20px;border:1px solid var(--amber);padding:14px;background:#fff8ed;color:#633600}}
@media(max-width:900px){{.domains{{grid-template-columns:1fr}}.metrics{{grid-template-columns:1fr 1fr}}.pipeline{{grid-template-columns:1fr 1fr 1fr}}}}
@media(max-width:560px){{main{{padding:20px 12px 40px}}header{{align-items:start;flex-direction:column}}h1{{font-size:28px}}.metrics,.facts,.split{{grid-template-columns:1fr}}.pipeline{{grid-template-columns:1fr 1fr}}.metric{{border-bottom:1px solid #3c4441}}.eval-table thead{{display:none}}.eval-table table,.eval-table tbody,.eval-table tr,.eval-table td{{display:block;width:100%}}.eval-table tr{{border:1px solid var(--line);padding:4px 8px;margin-bottom:8px}}.eval-table td{{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:6px 0;text-align:right;border-bottom:1px dotted var(--line);overflow-wrap:anywhere}}.eval-table td:last-child{{border-bottom:0}}.eval-table td::before{{content:attr(data-label);color:var(--muted);font-size:10px;text-transform:uppercase;text-align:left}}.run-name{{text-align:right;min-width:0}}}}
</style>
</head>
<body><main>
<header><div><div class="brand">LANGQI FORGE / 琅岐铸造</div><h1>Evidence before confidence.</h1><p class="subtitle">一次受约束的模型决策，把需求路由到可运行内核；失败变成最小反例，全绿才铸成能力胶囊，下次复用仍不免检。</p></div><span class="status {verdict_class}">{_escape(verdict)}</span></header>
<section class="metrics">
  <div class="metric"><b>{totals['passed_tests']} / {totals['expected_tests']}</b><span>locked public GUI</span></div>
  <div class="metric"><b>{totals['requirements']}</b><span>compiled atomic requirements</span></div>
  <div class="metric"><b>{totals['prompt_tokens']} + {totals['completion_tokens']}</b><span>planner input + output tokens</span></div>
  <div class="metric"><b>{totals['manual_interventions']}</b><span>manual interventions</span></div>
</section>
<section class="pipeline">
  <div><b>01 Compile</b><span>deterministic requirements</span></div><div><b>02 Decide</b><span>forced model tool call</span></div><div><b>03 Route</b><span>closed-world coverage</span></div><div><b>04 Build</b><span>kernel or bounded delta</span></div><div><b>05 Falsify</b><span>baseline + adversarial GUI</span></div><div><b>06 Remember</b><span>capsule, never skip recheck</span></div>
</section>
<div class="domains">{cards}</div>
<aside class="boundary"><strong>Claim boundary.</strong> {_escape(data['claim_boundary'])}</aside>
</main></body></html>
"""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a self-contained judge view from sealed Langqi Forge artifacts"
    )
    parser.add_argument("--github-project", type=Path, required=True)
    parser.add_argument("--sheet-project", type=Path, required=True)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output = _safe_output(args.output)
    requested_data_output = args.data_output or output.with_suffix(".json")
    if requested_data_output.expanduser().resolve() == output:
        raise ValueError("HTML and JSON judge report outputs must be different files")
    data_output = _safe_output(requested_data_output)
    data = build_report_data(
        args.github_project,
        args.sheet_project,
        args.qualification,
    )
    _write_text_atomic(output, render_report(data))
    atomic_write_json(data_output, data)
    print(
        json.dumps(
            {"html": str(output), "data": str(data_output), "totals": data["totals"]},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
