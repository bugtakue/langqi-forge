"""Forge orchestrator: plan -> seed + tests -> implement units -> test/repair -> regression -> deliver."""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import shutil
import sys
import time
import traceback
from pathlib import Path

from . import prompts as P
from .appctl import App
from .arcrt import ArcRuntime
from .llm import LLM, LLMError
from .spec import Atomic, Spec, group_units, load_spec
from .workspace import Workspace, copy_scaffold

HERE = Path(__file__).resolve().parent
T0 = time.time()
# Roles (first dash-separated token of the call tag) that keep model reasoning on by default.
THINK_DEFAULT_ON = {"plan"}


class Agent:
    def __init__(self, req_dir: Path, out_dir: Path) -> None:
        self.req_dir = Path(req_dir).resolve()
        self.out = Path(out_dir).resolve()
        self.forge_dir = self.out / ".arc" / "forge"
        self.forge_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = open(self.forge_dir / "forge.log", "a", encoding="utf-8")
        self.time_limit = float(os.environ.get("FORGE_TIME_LIMIT_MIN", "300")) * 60
        self.max_repairs = int(os.environ.get("FORGE_MAX_REPAIRS", "2"))
        self.parallel = int(os.environ.get("FORGE_PARALLEL", "6"))
        self.max_tokens = int(os.environ.get("FORGE_MAX_TOKENS", "32000"))
        model = os.environ.get("FORGE_MODEL") or os.environ.get("MODEL") or "deepseek-v4-flash"
        self.llm = LLM(model=model, log=self.log)
        self.code_model = os.environ.get("FORGE_CODE_MODEL") or model
        self.plan_model = os.environ.get("FORGE_PLAN_MODEL") or model
        self.test_model = os.environ.get("FORGE_TEST_MODEL") or model
        self.ws = Workspace(self.out, extra_allowed=(".arc/forge/tests/",))
        self.app = App(self.out, port=int(os.environ.get("FORGE_DEV_PORT", "3100")), log=self.log)
        self.rt = ArcRuntime.connect(self.out, self.log)
        self.report: dict = {"units": [], "events": []}
        self.unit_state: dict[int, dict] = {}
        self.tests: dict[int, Path | None] = {}
        self.units: list = []

    # ------------------------------------------------------------------ utils
    def log(self, msg: str) -> None:
        line = f"[{time.time() - T0:7.0f}s] {msg}"
        print(line, flush=True)
        try:
            self.log_file.write(line + "\n")
            self.log_file.flush()
        except Exception:
            pass

    def elapsed(self) -> float:
        return time.time() - T0

    def remaining(self) -> float:
        return self.time_limit - self.elapsed()

    def ask(self, system: str, user: str, model: str, tag: str, max_tokens: int | None = None) -> str:
        role = tag.split("-")[0]
        think = os.environ.get(f"FORGE_THINK_{role.upper()}", "1" if role in THINK_DEFAULT_ON else "0") == "1"
        return self.llm.chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                             model=model, max_tokens=max_tokens or self.max_tokens, tag=tag, timeout=1500,
                             think=None if think else False)

    def save_report(self) -> None:
        self.report["usage"] = self.llm.usage.snapshot()
        self.report["elapsed_s"] = round(self.elapsed())
        (self.forge_dir / "report.json").write_text(json.dumps(self.report, indent=1), encoding="utf-8")

    # ------------------------------------------------------------------ main
    def run(self) -> int:
        self.spec = load_spec(self.req_dir)
        self.units = group_units(self.spec)
        self.log(f"spec: {len(self.spec.atomics)} atomics, {len(self.units)} units, "
                 f"{sum(len(a.scenarios) for a in self.spec.atomics)} scenarios; model={self.llm.model}")
        copy_scaffold(HERE / "scaffold", self.out)
        if self.rt:
            self.rt.start(self.requirement_tree())

        self.arch = self.plan()
        self.file_plan = parse_file_plan(self.arch)
        self.arch_excerpt = arch_excerpt(self.arch)

        self.test_pool = cf.ThreadPoolExecutor(max_workers=self.parallel)
        self.test_futs = {i: self.test_pool.submit(self.write_tests, i, unit) for i, unit in enumerate(self.units)}
        with cf.ThreadPoolExecutor(max_workers=8) as seed_pool:
            self.seed(seed_pool)

        impl_times: list[float] = []
        for i, unit in enumerate(self.units):
            t = time.time()
            self.do_unit(i, unit, foundation=(i == 0), impl_times=impl_times)
            impl_times.append(time.time() - t)
            self.save_report()
            if i % 6 == 5 and self.remaining() > 1800:
                self.regression(repair=False)

        self.final_phase()
        return self.deliver()

    def test_file(self, idx: int) -> Path | None:
        if idx not in self.tests:
            fut = self.test_futs.get(idx)
            try:
                self.tests[idx] = fut.result(timeout=1800) if fut else None
            except Exception as exc:  # noqa: BLE001
                self.log(f"test writing failed for unit {idx}: {exc}")
                self.tests[idx] = None
        return self.tests[idx]

    def requirement_tree(self) -> dict:
        return yaml_load(self.req_dir / "requirements.yaml")

    # ------------------------------------------------------------------ planning
    def plan(self) -> str:
        path = self.forge_dir / "ARCHITECTURE.md"
        if path.exists() and os.environ.get("FORGE_REUSE_PLAN"):
            return path.read_text(encoding="utf-8")
        user = P.PLAN_USER.format(spec=self.spec.full_text())
        text = self.ask(P.PLAN_SYSTEM, user, self.plan_model, "plan", max_tokens=max(self.max_tokens, 32000))
        path.write_text(text, encoding="utf-8")
        self.log(f"architecture written ({len(text)} chars)")
        return text

    def seed(self, pool: cf.ThreadPoolExecutor) -> None:
        areas: dict[str, list[Atomic]] = {}
        for a in self.spec.atomics:
            key = a.ancestors[1]["id"] if len(a.ancestors) > 1 else a.id
            areas.setdefault(key, []).append(a)
        names = {f["id"]: f["name"] for f in self.spec.folders}

        def one(i: int, key: str, atoms: list[Atomic]) -> list[str]:
            seed_path = f"backend/seed/{10 + i:02d}-{re.sub(r'[^a-z0-9]+', '-', key.lower()).strip('-')}.js"
            scen = "\n\n".join(f"{a.id} {a.name}\n{a.render()}" for a in atoms)
            user = P.SEED_USER.format(seed_path=seed_path, area=f"{key} {names.get(key, '')}", arch=self.arch, scenarios=scen)
            text = self.ask(P.CODER_SYSTEM, user, self.code_model, f"seed-{key}")
            changed, errors = self.ws.apply(text)
            if not changed:
                blocks = re.findall(r"```(?:js|javascript)?\s*\n(.*?)```", text, re.S)
                code = max(blocks, key=len) if blocks else ""
                if "module.exports" in code:
                    self.ws.write(seed_path, code)
                    changed = [seed_path]
            self.log(f"seed-{key}: changed={changed} errors={errors}")
            return changed

        futs = [pool.submit(one, i, k, v) for i, (k, v) in enumerate(areas.items())]
        changed: list[str] = []
        for f in futs:
            try:
                changed += f.result()
            except Exception as exc:  # noqa: BLE001
                self.log(f"seed area failed: {exc}")
        problem = self.health()
        for attempt in range(2):
            if not problem:
                break
            self.fix_broken(problem, priority=changed, tag=f"seed-fix{attempt}")
            problem = self.health()
        if problem:
            self.log("seed still broken; removing seed file to keep app bootable")
            for f in changed:
                self.ws.path(f).unlink(missing_ok=True)

    def write_tests(self, idx: int, unit: list[Atomic]) -> Path | None:
        path = self.forge_dir / "tests" / f"test_u{idx:02d}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and os.environ.get("FORGE_REUSE_TESTS"):
            return path
        user = P.TEST_USER.format(context=unit[0].render_context(), arch_excerpt=self.arch_excerpt,
                                  requirements="\n\n".join(a.render() for a in unit))
        for attempt in range(2):
            text = self.ask(P.TEST_SYSTEM, user, self.test_model, f"tests-u{idx}", max_tokens=28000)
            code = extract_python(text)
            try:
                compile(code, str(path), "exec")
            except SyntaxError as exc:
                self.log(f"tests-u{idx} syntax error: {exc}")
                continue
            if "def test_" not in code:
                continue
            path.write_text(code, encoding="utf-8")
            return path
        return None

    # ------------------------------------------------------------------ health
    def health(self, smoke_paths: list[str] | None = None) -> str:
        """Return a problem description, or '' when the app builds, starts and loads."""
        errs = self.app.syntax_errors()
        if errs:
            return "Syntax errors:\n" + "\n\n".join(errs[:6])
        ok, out = self.app.build()
        if not ok:
            return "Frontend build failed:\n" + out
        ok, out = self.app.start(fresh=True)
        if not ok:
            return out
        time.sleep(0.3)
        log = self.app.server_log(20000)
        if "failed to load" in log:
            return "Backend module failed to load at startup (the module was skipped):\n" + log[-4000:]
        errs = self.app.browser_smoke(smoke_paths or ["/"])
        if errs:
            return "Browser errors while loading the app:\n" + "\n".join(errs[:10]) + "\nServer log:\n" + self.app.server_log(1500)
        return ""

    def fix_broken(self, problem: str, priority: list[str], tag: str) -> None:
        prio = self.referenced_files(problem) + priority + self.shared_files()
        files, _ = self.ws.context_files(prio, budget_chars=80000)
        text = self.ask(P.CODER_SYSTEM, P.FIX_BROKEN_USER.format(problem=problem[:6000], arch=self.arch, files=files),
                        self.code_model, tag, max_tokens=24000)
        changed, errors = self.ws.apply(text)
        self.log(f"{tag}: changed={changed} errors={errors}")

    def referenced_files(self, text: str) -> list[str]:
        found = re.findall(r"((?:frontend/src|backend)/[\w./-]+\.js)", text)
        found += ["frontend/src/" + m for m in re.findall(r"https?://[^/\s]+/((?:pages|lib)/[\w./-]+\.js)", text)]
        return [f for f in dict.fromkeys(found) if self.ws.path(f).exists()]

    def shared_files(self) -> list[str]:
        out = ["frontend/src/shell.js"]
        for f in self.ws.editable_files():
            if f.startswith(("frontend/src/lib/", "backend/lib/")):
                out.append(f)
        return out

    def unit_files(self, unit: list[Atomic], include_deps: bool = True) -> list[str]:
        files: list[str] = []
        for a in unit:
            files += self.file_plan.get(a.id, [])
        if include_deps:
            for a in unit:
                for d in a.deps:
                    files += self.file_plan.get(d, [])
        home = [f for f in self.ws.editable_files() if re.search(r"pages/(home|index|dashboard)\.js$", f)]
        seeds = [f for f in self.ws.editable_files() if f.startswith("backend/seed/")]
        return list(dict.fromkeys(files + self.shared_files() + home + seeds))

    # ------------------------------------------------------------------ units
    def do_unit(self, idx: int, unit: list[Atomic], foundation: bool, impl_times: list[float]) -> None:
        ids = [a.id for a in unit]
        state = {"ids": ids, "implemented": False, "passed": 0, "total": 0, "repairs": 0}
        self.unit_state[idx] = state
        self.report["units"].append(state)
        self.log(f"=== unit {idx}/{len(self.units) - 1}: {ids}")
        if self.rt:
            self.rt.impl_started(ids)
        snap = self.ws.snapshot()
        try:
            self.implement(idx, unit, foundation)
        except LLMError as exc:
            self.log(f"unit {idx} implement failed: {exc}")
            self.ws.restore(snap)
            if self.rt:
                self.rt.impl_failed(ids, str(exc))
            return
        problem = self.health()
        for attempt in range(2):
            if not problem:
                break
            self.log(f"unit {idx} broke the app: {problem[:400]}")
            try:
                self.fix_broken(problem, self.unit_files(unit), tag=f"u{idx}-fix{attempt}")
            except LLMError:
                break
            problem = self.health()
        if problem:
            self.log(f"unit {idx}: reverting (app still broken)")
            self.ws.restore(snap)
            self.health()
            if self.rt:
                self.rt.impl_failed(ids, "reverted: app broken")
            return
        state["implemented"] = True
        if self.rt:
            self.rt.impl_done(ids)
            self.rt.commit(f"implement {', '.join(ids)}")
        self.test_and_repair(idx, unit, impl_times)

    def implement(self, idx: int, unit: list[Atomic], foundation: bool) -> None:
        prio = self.unit_files(unit)
        files, omitted = self.ws.context_files(prio, budget_chars=100000)
        user = P.IMPLEMENT_USER.format(
            foundation=P.FOUNDATION_NOTE if foundation else "",
            arch=self.arch, files=files, other_files="\n".join(omitted) or "(none)",
            context=unit[0].render_context(), requirements="\n\n".join(a.render() for a in unit))
        text = self.ask(P.CODER_SYSTEM, user, self.code_model, f"impl-u{idx}")
        (self.forge_dir / "responses").mkdir(exist_ok=True)
        (self.forge_dir / "responses" / f"impl-u{idx:02d}.txt").write_text(text, encoding="utf-8")
        changed, errors = self.ws.apply(text)
        self.log(f"impl-u{idx}: changed={changed} errors={errors}")
        if errors and not changed:
            raise LLMError("implementation produced no applicable changes: " + "; ".join(errors)[:500])
        if errors:
            # One quick follow-up to resolve failed edits.
            files, _ = self.ws.context_files(changed + prio, budget_chars=80000)
            follow = (f"Some of your file operations could not be applied:\n" + "\n".join(errors) +
                      "\nRe-emit corrected operations for those changes only (use FILE blocks for full files).\n\n"
                      f"# CURRENT FILES\n{files}\n\n# REQUIREMENTS\n" + "\n\n".join(a.render(False) for a in unit))
            text2 = self.ask(P.CODER_SYSTEM, follow, self.code_model, f"impl-u{idx}-reapply", max_tokens=24000)
            c2, e2 = self.ws.apply(text2)
            self.log(f"impl-u{idx} reapply: changed={c2} errors={e2}")

    def test_and_repair(self, idx: int, unit: list[Atomic], impl_times: list[float]) -> None:
        state = self.unit_state[idx]
        test_path = self.test_file(idx)
        if not test_path or not test_path.exists():
            return
        results = self.run_unit_tests(idx)
        best = (sum(r["ok"] for r in results), self.ws.snapshot(), test_path.read_text())
        for rnd in range(self.max_repairs):
            fails = [r for r in results if not r["ok"]]
            if not fails:
                break
            units_left = len(self.units) - idx - 1
            avg = (sum(impl_times) / len(impl_times)) if impl_times else 300
            if self.remaining() < units_left * avg * 0.8 + 1200:
                self.log(f"unit {idx}: skipping repair (time budget)")
                break
            state["repairs"] += 1
            try:
                self.repair(idx, unit, test_path, fails, tag=f"repair-u{idx}-r{rnd}")
            except LLMError as exc:
                self.log(f"repair failed: {exc}")
                break
            problem = self.health()
            if problem:
                self.log(f"repair broke app; restoring best: {problem[:300]}")
                self.ws.restore(best[1])
                test_path.write_text(best[2])
                self.health()
                break
            results = self.run_unit_tests(idx)
            passed = sum(r["ok"] for r in results)
            if passed >= best[0]:
                best = (passed, self.ws.snapshot(), test_path.read_text())
            else:
                self.log(f"unit {idx}: repair regressed ({passed} < {best[0]}); restoring")
                self.ws.restore(best[1])
                test_path.write_text(best[2])
                self.health()
                results = self.run_unit_tests(idx)
        state["passed"] = sum(r["ok"] for r in results)
        state["total"] = len(results)
        if self.rt:
            for a in unit:
                self.rt.test_result(a.id, state["passed"] == state["total"], f"local {state['passed']}/{state['total']}")
            self.rt.commit(f"verify {', '.join(state['ids'])}: {state['passed']}/{state['total']} local tests")

    def run_unit_tests(self, idx: int) -> list[dict]:
        ok, out = self.app.start(fresh=True)
        if not ok:
            return [{"test": "<startup>", "ok": False, "error": out}]
        results = self.app.run_tests([self.tests[idx]])
        passed = sum(r["ok"] for r in results)
        self.log(f"unit {idx} tests: {passed}/{len(results)} " +
                 " ".join(f"{r['test']}={'ok' if r['ok'] else 'FAIL'}" for r in results))
        return results

    def repair(self, idx: int, unit: list[Atomic], test_path: Path, fails: list[dict], tag: str) -> None:
        failures = "\n\n".join(f"## {r['test']}\n{r['error'][:2500]}" for r in fails)
        prio = self.referenced_files(failures) + self.unit_files(unit)
        files, omitted = self.ws.context_files(prio, budget_chars=90000)
        rel_test = str(test_path.relative_to(self.out))
        user = P.REPAIR_USER.format(arch=self.arch, requirements="\n\n".join(a.render() for a in unit),
                                    test_path=rel_test, test_code=test_path.read_text(), failures=failures,
                                    server_log=self.app.server_log(2000), files=files,
                                    other_files="\n".join(omitted) or "(none)")
        text = self.ask(P.CODER_SYSTEM, user, self.code_model, tag)
        (self.forge_dir / "responses" / f"{tag}.txt").write_text(text, encoding="utf-8")
        changed, errors = self.ws.apply(text)
        self.log(f"{tag}: changed={changed} errors={errors}")

    # ------------------------------------------------------------------ regression & delivery
    def regression(self, repair: bool) -> dict[int, list[dict]]:
        files = [self.tests[i] for i in sorted(self.unit_state) if self.tests.get(i) and self.unit_state[i]["implemented"]]
        if not files:
            return {}
        ok, out = self.app.start(fresh=True)
        if not ok:
            self.log("regression: app failed to start")
            return {}
        results = self.app.run_tests(files, timeout=1800)
        by_unit: dict[int, list[dict]] = {}
        for r in results:
            m = re.search(r"test_u(\d+)\.py", r["file"])
            if m:
                by_unit.setdefault(int(m.group(1)), []).append(r)
        total = sum(r["ok"] for r in results)
        self.log(f"regression: {total}/{len(results)} passed; per unit: " +
                 ", ".join(f"u{i}={sum(x['ok'] for x in rs)}/{len(rs)}" for i, rs in sorted(by_unit.items())))
        self.report["events"].append({"regression": total, "of": len(results), "t": round(self.elapsed())})
        return by_unit

    def final_phase(self) -> None:
        if self.remaining() < 900:
            return
        by_unit = self.regression(repair=False)
        if not by_unit:
            return
        base_total = sum(sum(r["ok"] for r in rs) for rs in by_unit.values())
        best_snap = self.ws.snapshot()
        order = sorted(by_unit, key=lambda i: -sum(not r["ok"] for r in by_unit[i]))
        repaired = False
        for i in order:
            fails = [r for r in by_unit[i] if not r["ok"]]
            if not fails or self.remaining() < 1500:
                continue
            try:
                self.repair(i, self.units[i], self.tests[i], fails, tag=f"final-u{i}")
            except LLMError:
                continue
            if self.health():
                self.ws.restore(best_snap)
                self.health()
                continue
            repaired = True
            best_snap = self.ws.snapshot()
        if repaired and self.remaining() > 600:
            after = self.regression(repair=False)
            after_total = sum(sum(r["ok"] for r in rs) for rs in after.values())
            self.log(f"final phase: {base_total} -> {after_total}")

    def deliver(self) -> int:
        pool = getattr(self, "test_pool", None)
        if pool:
            pool.shutdown(wait=False, cancel_futures=True)
        problem = self.health()
        if problem:
            self.log(f"final health problem: {problem[:800]}")
            try:
                self.fix_broken(problem, self.shared_files(), tag="final-fix")
            except LLMError:
                pass
            problem = self.health()
        self.app.stop()
        shutil.rmtree(self.out / "backend" / "data", ignore_errors=True)
        shutil.rmtree(self.out / "frontend" / "dist", ignore_errors=True)
        self.save_report()
        done = sum(1 for s in self.unit_state.values() if s["implemented"])
        passed = sum(s["passed"] for s in self.unit_state.values())
        total = sum(s["total"] for s in self.unit_state.values())
        msg = f"units implemented {done}/{len(self.units)}; local tests {passed}/{total}"
        self.log("DONE: " + msg + f"; usage={self.llm.usage.snapshot()}")
        if self.rt:
            self.rt.commit("final delivery")
            if problem:
                self.rt.fail("final app unhealthy: " + problem[:300])
            else:
                self.rt.complete(msg)
        return 0 if not problem else 1


# ---------------------------------------------------------------------- helpers
def yaml_load(path: Path) -> dict:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def extract_python(text: str) -> str:
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    if blocks:
        return max(blocks, key=len)
    return text


def parse_file_plan(arch: str) -> dict[str, list[str]]:
    blocks = re.findall(r"```json\s*\n(.*?)```", arch, re.S)
    for block in reversed(blocks):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and any(str(k).startswith("REQ") for k in data):
            return {str(k): [str(f) for f in v] for k, v in data.items() if isinstance(v, list)}
    return {}


def arch_excerpt(arch: str) -> str:
    """Overview, Pages and Seed sections only (for test writers)."""
    sections = re.split(r"(?m)^(?=#{1,3} )", arch)
    keep = [s for s in sections if re.match(r"#{1,3} .*(Overview|Pages|Seed|Shell)", s, re.I)]
    return "\n".join(keep) if keep else arch[:20000]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("requirements_dir")
    parser.add_argument("--output-dir", required=True)
    args, _ = parser.parse_known_args(argv)
    agent = Agent(Path(args.requirements_dir), Path(args.output_dir))
    try:
        return agent.run()
    except Exception as exc:  # noqa: BLE001
        agent.log("FATAL: " + traceback.format_exc())
        try:
            return agent.deliver()
        except Exception:
            if agent.rt:
                agent.rt.fail(str(exc))
            return 1
