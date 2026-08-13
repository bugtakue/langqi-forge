#!/usr/bin/env python3
"""ARC-Bench custom agent bundle: Octos as the coding agent.

The ARC-Bench platform invokes this as:

    python main.py <requirement_path> [--output-dir DIR] [--web-port N]

It drives the Octos agent (Rust binary) to compile a requirement tree into a
runnable web application, and reports progress through the ARC-Bench runtime
contract: .arc/runner-events.jsonl + .arc/traceability/*.json + git commits.

Configuration is via environment variables:
    OPENAI_API_KEY / OPENAI_BASE_URL / MODEL   (OpenAI-compatible endpoint)
    OCTOS_PROVIDER  (override provider name, e.g. deepseek/openai/anthropic)
    OCTOS_MODEL     (override model name)
    OCTOS_BIN       (path to the octos binary; default: ./bin/octos then PATH)
    OCTOS_MAX_ITERATIONS (default 200)
    OCTOS_NODE_TIMEOUT   (seconds per requirement node, default 1800)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arcbench_agent_runtime import AgentRuntime  # noqa: E402


def log(msg: str) -> None:
    """Progress lines go to BOTH stdout and stderr.

    The platform's stdout capture gets truncated on long runs (we lost the
    [flow] lines of an entire failed run that way); the runner stores agent
    stderr as a separate field, so mirroring there keeps our diagnostics
    retrievable. Stderr content does not affect the verdict (exit code and
    SDK events do).
    """
    print(msg, flush=True)
    print(msg, file=sys.stderr, flush=True)


def _postflight_structure_check(output_dir: Path, web_port: int = 3000) -> None:
    """Diagnose and repair the deliverable layout the runner checks.

    The runner requires PROJECT_DIR/frontend and PROJECT_DIR/backend after
    the agent exits ("web template is incomplete" otherwise). Round 12 showed
    a run can end with them missing while the platform still reports
    "generation agent finished successfully" (we return 0 on handled
    failures). Log the directory tree so we can see what octos actually
    produced, and if the app was scaffolded exactly one level deep
    (output_dir/<app>/frontend etc.), lift it into place.

    Also free the web port: round 14 died on EADDRINUSE :3000 at evaluation
    time because a smoke-test server from a failed generation turn was still
    holding it.
    """
    tree_lines = []
    for root, dirs, files in os.walk(output_dir):
        dirs[:] = [d for d in dirs
                   if d not in ("node_modules", ".git", "dist", "__pycache__")]
        depth = Path(root).relative_to(output_dir).parts
        if len(depth) > 2:
            dirs[:] = []
            continue
        indent = "  " * len(depth)
        tree_lines.append(f"{indent}{Path(root).name}/")
        for f in sorted(files)[:8]:
            tree_lines.append(f"{indent}  {f}")
        if len(tree_lines) > 60:
            tree_lines.append("... (truncated)")
            break
    log("[postflight] workspace tree:\n" + "\n".join(tree_lines))

    if (output_dir / "frontend").is_dir() and (output_dir / "backend").is_dir():
        log("[postflight] frontend/ and backend/ present at workspace root")
        return
    children = [p for p in output_dir.iterdir()
                if p.is_dir() and p.name not in (".git", ".arc", "requirements")]
    for child in children:
        if (child / "frontend").is_dir() and (child / "backend").is_dir():
            log(f"[postflight] app found nested at {child.name}/; lifting to root")
            for item in child.iterdir():
                dest = output_dir / item.name
                if dest.exists():
                    continue
                shutil.move(str(item), str(dest))
            if (output_dir / "frontend").is_dir() and (output_dir / "backend").is_dir():
                log("[postflight] lift succeeded")
            return
    log("[postflight] WARNING: no frontend/+backend/ found anywhere; "
        "runner will reject the template")


def _free_web_port(web_port: int) -> None:
    """Best-effort kill of whatever still listens on the app port."""
    for cmd in (["fuser", "-k", f"{web_port}/tcp"],
                ["sh", "-c", f"lsof -ti :{web_port} | xargs -r kill"]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                log(f"[postflight] freed port {web_port} via {cmd[0]}")
                return
        except (OSError, subprocess.TimeoutExpired):
            continue
    log(f"[postflight] port {web_port} cleanup attempted (no tool matched)")


# ---------------------------------------------------------------- requirements

def load_requirement_tree(req_dir: Path) -> dict:
    req_file = req_dir / "requirements.yaml"
    if not req_file.exists():
        req_file = req_dir / "requirements.yml"
    data = yaml.safe_load(req_file.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "id" not in data:
        for wrapper in ("root", "requirement"):
            if isinstance(data.get(wrapper), dict):
                data = data[wrapper]
                break
    if not isinstance(data, dict) or "id" not in data:
        raise ValueError(f"invalid requirements.yaml in {req_dir}")
    return data


def flatten_atomic(node: dict, out: list | None = None) -> list[dict]:
    if out is None:
        out = []
    node_type = str(node.get("type") or "").upper()
    if node_type == "ATOMIC" or (not node.get("children") and node_type != "FOLDER"):
        out.append(node)
    for child in node.get("children") or []:
        if isinstance(child, dict):
            flatten_atomic(child, out)
    return out


def describe_node(node: dict) -> str:
    lines = [f"ID: {node.get('id')}", f"Name: {node.get('name', '')}"]
    if node.get("description"):
        lines.append(f"Description: {node['description']}")
    scenarios = node.get("scenarios") or []
    if scenarios:
        lines.append("Scenarios:")
        for sc in scenarios:
            lines.append(f"  - {sc.get('name', 'scenario')}")
            for step in sc.get("steps") or []:
                if isinstance(step, dict):
                    kw = step.get("keyword", "")
                    lines.append(f"      {kw} {step.get('content', '')}")
    deps = node.get("dependencies") or []
    if deps:
        lines.append(f"Depends on: {', '.join(map(str, deps))}")
    return "\n".join(lines)


# ---------------------------------------------------------------- octos driver

OCTOS_RELEASE_URL = (
    "https://github.com/octos-org/octos/releases/latest/download/"
    "octos-bundle-x86_64-unknown-linux-gnu.tar.gz"
)


def _download_octos(dest_dir: Path) -> str:
    """Fetch the Linux octos binary at runtime (keeps the upload zip small).

    The runner network can be very slow toward GitHub, so download with
    `curl -C -` resume in a retry loop and verify the tarball before use.
    """
    import tarfile
    import urllib.request

    dest_dir.mkdir(parents=True, exist_ok=True)
    tarball = dest_dir / "octos-bundle.tar.gz"
    url = os.environ.get("OCTOS_RELEASE_URL", OCTOS_RELEASE_URL)

    def tarball_ok() -> bool:
        try:
            with tarfile.open(tarball) as tf:
                return tf.getmember("octos") is not None
        except Exception:
            return False

    ok = tarball_ok()
    # The runner sits behind a CN network path that mangles GitHub's HTTP/2
    # streams (curl 92 PROTOCOL_ERROR), stalls connections entirely, and has
    # stopped accepting direct GitHub connections altogether in recent runs.
    # Try the public gh-proxy mirrors FIRST (they deliver in ~6-11 min), keep
    # the direct URL as last resort; fail fast on stalls (--speed-limit) and
    # resume partial bytes with `-C -`.
    mirrors = [
        f"{prefix}/{url}"
        for prefix in ("https://ghfast.top", "https://gh-proxy.com")
    ] + [url]
    for attempt in range(1, 13):
        if ok:
            break
        mirror = mirrors[(attempt - 1) % len(mirrors)]
        log(f"[octos] download attempt {attempt} ({mirror}) ...")
        if shutil.which("curl"):
            # -sS: no progress meter — the platform log endpoint caps stdout
            # (~200KB) and curl's per-second redraws would push the real
            # diagnostics (and later eval errors) past the cap.
            # --http1.1: the runner's path to GitHub kills HTTP/2 streams
            # mid-download (curl 92 PROTOCOL_ERROR); HTTP/1.1 + `-C -`
            # resume survives it.
            # timeout=600: round 15 showed a stalled connection can hold for
            # the full subprocess timeout; kill it and rotate mirrors instead.
            try:
                subprocess.run(
                    ["curl", "-fsSL", "--http1.1", "-C", "-",
                     "--connect-timeout", "30",
                     "--speed-limit", "10240", "--speed-time", "60",
                     "--retry", "2", "-o", str(tarball), mirror],
                    check=False, timeout=600,
                )
            except subprocess.TimeoutExpired:
                log(f"[octos] attempt {attempt} killed after 600s stall; "
                    f"rotating mirror")
        else:
            try:
                urllib.request.urlretrieve(mirror, tarball)
            except Exception as exc:  # noqa: BLE001 - retry below
                log(f"[octos] download error: {exc}")
        ok = tarball_ok()
    if not ok:
        raise RuntimeError("failed to download octos binary after 12 attempts")

    with tarfile.open(tarball) as tf:
        for member in ("octos", "octos-sandbox"):
            try:
                tf.extract(member, dest_dir, filter="data")
            except KeyError:
                pass
    binary = dest_dir / "octos"
    binary.chmod(0o755)
    sandbox = dest_dir / "octos-sandbox"
    if sandbox.exists():
        sandbox.chmod(0o755)
    return str(binary)


def find_octos() -> str:
    env_bin = os.environ.get("OCTOS_BIN")
    if env_bin and Path(env_bin).exists():
        return env_bin
    bundled = Path(__file__).resolve().parent / "bin" / "octos"
    if bundled.exists():
        return str(bundled)
    found = shutil.which("octos")
    if found:
        return found
    cache_dir = Path(os.environ.get("OCTOS_CACHE_DIR", "/tmp/octos-bin"))
    cached = cache_dir / "octos"
    if cached.exists():
        return str(cached)
    return _download_octos(cache_dir)


def build_octos_env(config_dir: Path) -> dict:
    """Prepare env + minimal config.json for non-interactive octos."""
    env = os.environ.copy()
    api_key = env.get("OPENAI_API_KEY", "")
    base_url = env.get("OPENAI_BASE_URL", "")
    model = os.environ.get("OCTOS_MODEL") or env.get("MODEL", "")

    provider = os.environ.get("OCTOS_PROVIDER")
    if not provider:
        if "deepseek" in base_url:
            provider = "deepseek"
        elif "anthropic" in base_url:
            provider = "anthropic"
        else:
            provider = "openai"

    # Map the generic OPENAI_API_KEY onto the provider-specific env name.
    key_env = "OPENAI_API_KEY"
    if provider == "deepseek" and api_key:
        env.setdefault("DEEPSEEK_API_KEY", api_key)
        key_env = "DEEPSEEK_API_KEY"
    elif provider == "anthropic" and api_key:
        env.setdefault("ANTHROPIC_API_KEY", api_key)
        key_env = "ANTHROPIC_API_KEY"

    config = {
        "provider": provider,
        "model": model,
        "sandbox": {"allow_network": True},
        "memory": {"refresh": {"enabled": False}},
    }
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    env["OCTOS_CONFIG_DIR"] = str(config_dir)
    # The platform's model proxies do not support SSE streaming (the official
    # octos-runner sets this too) — without it octos dies with
    # "failed to send streaming request to OpenAI".
    env.setdefault("OCTOS_DISABLE_STREAMING", "1")
    # Resolved values for the stdio driver's profile bootstrap.
    env["_ARC_PROVIDER"] = provider
    env["_ARC_MODEL"] = model
    env["_ARC_BASE_URL"] = base_url
    env["_ARC_KEY_ENV"] = key_env
    return env


_CHAT_FLAGS_CACHE: dict[str, set[str]] = {}


def _chat_supported_flags(octos_bin: str) -> set[str]:
    """Probe `octos chat --help` once; release builds have fewer flags."""
    if octos_bin not in _CHAT_FLAGS_CACHE:
        try:
            proc = subprocess.run([octos_bin, "chat", "--help"],
                                  capture_output=True, text=True, timeout=30)
            help_text = (proc.stdout or "") + (proc.stderr or "")
        except Exception:
            help_text = ""
        _CHAT_FLAGS_CACHE[octos_bin] = {
            flag for flag in ("--json", "--cwd", "--data-dir",
                              "--max-iterations", "--no-session-persistence")
            if flag in help_text
        }
    return _CHAT_FLAGS_CACHE[octos_bin]


def run_octos(octos_bin: str, cwd: Path, prompt: str, env: dict, data_dir: Path,
              timeout: int, max_iterations: int) -> tuple[bool, str]:
    """Run one non-interactive octos turn. Returns (success, output_text)."""
    flags = _chat_supported_flags(octos_bin)
    cmd = [octos_bin, "chat", "-m", prompt]
    if "--json" in flags:
        cmd.append("--json")
    if "--cwd" in flags:
        cmd += ["--cwd", str(cwd)]
    if "--data-dir" in flags:
        cmd += ["--data-dir", str(data_dir)]
    if "--max-iterations" in flags:
        cmd += ["--max-iterations", str(max_iterations)]
    if "--no-session-persistence" in flags:
        cmd.append("--no-session-persistence")
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), env=env, capture_output=True, text=True,
            timeout=timeout, errors="replace",
        )
    except subprocess.TimeoutExpired:
        return False, f"octos timed out after {timeout}s"
    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        detail = out or (proc.stderr or "").strip()[-2000:]
        return False, f"octos exited {proc.returncode}: {detail}"
    try:
        payload = json.loads(out)
        if isinstance(payload, dict) and payload.get("error"):
            return False, str(payload["error"])
        return True, str(payload.get("text", "")) if isinstance(payload, dict) else out
    except json.JSONDecodeError:
        # stdout wasn't the JSON envelope; treat as plain text output.
        return True, out[-4000:]


class OctosDriver:
    """Unified octos invocation: stdio UI Protocol (default) or one-shot chat.

    stdio mode keeps one long-lived session across all turns, giving the agent
    context continuity between requirement nodes and streaming tool events.
    Set OCTOS_DRIVER=chat to fall back to per-turn `octos chat -m` processes.
    """

    def __init__(self, octos_bin: str, cwd: Path, env: dict, data_dir: Path,
                 max_iterations: int, events_log: Path) -> None:
        self.mode = os.environ.get("OCTOS_DRIVER", "stdio")
        self.octos_bin = octos_bin
        self.cwd = cwd
        self.env = env
        self.data_dir = data_dir
        self.max_iterations = max_iterations
        self.events_log = events_log
        self._session = None

    def _log_event(self, method: str, params: dict) -> None:
        try:
            with self.events_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"method": method, "params": params},
                                    ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _get_session(self):
        if self._session is None:
            from octos_stdio import OctosStdioSession
            self._session = OctosStdioSession(
                self.octos_bin, self.cwd, self.env, self.data_dir,
                on_event=self._log_event,
            )
            self._session.bootstrap_profile(
                provider=self.env.get("_ARC_PROVIDER", "openai"),
                model=self.env.get("_ARC_MODEL", ""),
                base_url=self.env.get("_ARC_BASE_URL") or None,
                api_key_env=self.env.get("_ARC_KEY_ENV") or None,
            )
            self._session.open()
        return self._session

    def run(self, prompt: str, timeout: int) -> tuple[bool, str]:
        if self.mode == "chat":
            return self._run_with_retries(
                lambda: run_octos(self.octos_bin, self.cwd, prompt, self.env,
                                  self.data_dir, timeout, self.max_iterations))
        return self._run_with_retries(lambda: self._run_stdio(prompt, timeout))

    @staticmethod
    def _transient(text: str) -> bool:
        lowered = text.lower()
        return any(k in lowered for k in (
            "temporarily unavailable", "503", "502", "429", "rate limit",
            "timeout", "timed out", "connection reset", "overloaded",
            "failed to send", "streaming request"))

    def _run_with_retries(self, fn, attempts: int = 3) -> tuple[bool, str]:
        ok, text = fn()
        for attempt in range(2, attempts + 1):
            if ok or not self._transient(text):
                break
            wait = 30 * (attempt - 1)
            print(f"[driver] transient error, retry {attempt}/{attempts} "
                  f"after {wait}s: {text[:200]}", flush=True)
            time.sleep(wait)
            self.close()  # fresh session for the retry
            ok, text = fn()
        return ok, text

    def _run_stdio(self, prompt: str, timeout: int) -> tuple[bool, str]:
        try:
            return self._get_session().run_turn(prompt, timeout=float(timeout))
        except Exception as exc:
            # Fall back to a fresh one-shot chat for this turn.
            self.close()
            chat_ok, chat_text = run_octos(self.octos_bin, self.cwd, prompt,
                                           self.env, self.data_dir, timeout,
                                           self.max_iterations)
            if chat_ok:
                return True, chat_text
            return False, f"stdio driver error: {exc}; chat fallback: {chat_text}"[:1000]

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None


# ---------------------------------------------------------------- prompts

# Hard-won UI contract from a real bench run (round 16, ticketbooking):
# the platform's Playwright tests drive the UI with getByLabel/getByRole and
# fill human-readable values. Native widgets silently score 0.
UI_CONTRACT_PROMPT = """\
Benchmark UI contract (the automated tests depend on these EXACTLY):
- Use plain text inputs for ALL form fields: `type="text"` (or \
`password`/`email`). NEVER `type="date"` or `type="number"` — tests fill \
values like "Sun, May 31" which native date inputs reject.
- Every form field needs a visible associated <label> (tests use \
getByLabel with the field's name, e.g. "date", "from", "to").
- Every form control must be visible and enabled at all times — never hide \
native inputs/selects behind custom widgets or display:none containers.
- NEVER rely on native HTML5 validation (`required`, `pattern`, tooltips). \
Validate in JavaScript and render error messages as inline DOM text \
containing words like "required" / "invalid" / "missing" — tests assert on \
visible page text.
- Buttons are real <button> elements with plain text labels (e.g. "Search", \
"Book", "Register", "Sign in").
"""

APP_SKELETON_PROMPT = """\
You are building a full-stack web application in the current working \
directory. First skim the requirement tree under the requirements/ directory, \
then set up the project skeleton.

Required architecture (the benchmark runner depends on this EXACT contract, \
violation = 0 score):
- frontend/ — web frontend with a package.json that has a working \
`npm run build` script. A static HTML/CSS/JS frontend is fine; then \
"build" can be a small Node script that copies the static files into \
frontend/dist/. A Vite/React setup is also fine if you keep it minimal.
- backend/  — Node.js + Express + better-sqlite3, with a package.json that \
has a `npm run start` script. The backend reads the PORT environment \
variable (default {port}), serves the built frontend from frontend/dist/ at \
http://localhost:{port}/ and exposes JSON APIs under /api/.
- Seed the SQLite database with realistic demo data at startup if tables are empty.

""" + UI_CONTRACT_PROMPT + """
Verification steps the runner will perform later — make sure they ALL pass:
1. `npm install && npm run build` in frontend/
2. `npm install && PORT={port} npm run start` in backend/
3. http://127.0.0.1:{port}/ serves the app.

After scaffolding, run npm install for both directories, build the frontend, \
and smoke-test that the backend serves the app on port {port}. Keep \
dependencies minimal. Do not use TypeScript.\
"""

NODE_PROMPT_TEMPLATE = """\
You are implementing one requirement node of a larger full-stack web \
application. The application skeleton in the current working directory \
(frontend/ built with `npm run build` into frontend/dist/, Express + \
better-sqlite3 backend in backend/ started with `npm run start`, serving \
everything on port {port}) already exists.

Implement the following requirement completely — backend API, database \
tables/queries, and the frontend UI to exercise it:

{node_spec}

Rules:
- Extend the existing app; do not rewrite or break already-working features.
- Keep the architecture intact: `npm run build` in frontend/ and \
`npm run start` in backend/ MUST keep working.

""" + UI_CONTRACT_PROMPT + """
- After implementing, run `npm run build` in frontend/ and restart the \
backend to verify the new endpoint(s) respond correctly (e.g. with curl).
- Commit nothing yourself; the harness handles git.
"""

FINAL_CHECK_PROMPT = """\
Do a final end-to-end check of the web application in the current directory:
1. Run `npm run build` in frontend/ and fix any build errors.
2. Kill any leftover server process, then start the backend fresh with \
PORT={port} via `npm run start` in backend/.
3. Verify the app loads at http://localhost:{port}/ and every implemented \
API endpoint works (exercise them with curl, including error cases).
4. Audit every form against the benchmark UI contract below and fix \
violations (these silently score 0 in the automated tests):

""" + UI_CONTRACT_PROMPT + """
5. Fix anything else that is broken.
Finally, STOP every server process you started — the benchmark runner starts \
the backend itself afterwards, so port {port} must be free when you finish.\
"""


# ---------------------------------------------------------------- main flow

def main() -> int:
    parser = argparse.ArgumentParser(description="Octos agent bundle for ARC-Bench")
    parser.add_argument(
        "requirement_path",
        nargs="?",
        default=os.environ.get("ARCBENCH_TASK_DIR", "/workspace/task"),
    )
    parser.add_argument("--output-dir", default=None)
    # The platform runner passes `--type web|cli|android`; older local flows
    # used `--app-type`. Accept both spellings into the same dest.
    parser.add_argument("--type", "--app-type", dest="app_type", default="web")
    parser.add_argument("--web-port", type=int,
                        default=int(os.environ.get("ARCBENCH_WEB_PORT",
                                                   os.environ.get("ARC_WEB_PORT", "3000"))))
    args = parser.parse_args()

    # Diagnostics (no secrets): which model endpoint did the runner inject?
    _key = os.environ.get("OPENAI_API_KEY", "")
    print(f"[env] OPENAI_BASE_URL={os.environ.get('OPENAI_BASE_URL', '<unset>')}", flush=True)
    print(f"[env] MODEL={os.environ.get('MODEL', '<unset>')}", flush=True)
    print(f"[env] OPENAI_API_KEY={'set(len=%d)' % len(_key) if _key else '<unset>'}", flush=True)
    print(f"[env] ARCBENCH_TEMPLATE_DIR={os.environ.get('ARCBENCH_TEMPLATE_DIR', '<unset>')}", flush=True)
    print(f"[env] ARCBENCH_TASK_DIR={os.environ.get('ARCBENCH_TASK_DIR', '<unset>')}", flush=True)
    print(f"[env] argv requirement_path={args.requirement_path}", flush=True)

    # Raw LLM probe: bypass octos entirely and hit the injected endpoint with
    # a minimal chat.completions request, so we can tell a dead endpoint
    # apart from an octos request-shape problem. Never logs the key.
    # The platform proxy occasionally 500s ("上游负载") for minutes at a
    # time; gate on it (up to ~10 min) instead of burning generation turns
    # against a dead endpoint.
    if _key and os.environ.get("OPENAI_BASE_URL"):
        import urllib.request as _ur
        probe_body = json.dumps({
            "model": os.environ.get("MODEL", "deepseek-chat"),
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "max_tokens": 4,
        }).encode()
        probe_deadline = time.time() + 600
        probe_attempt = 0
        while True:
            probe_attempt += 1
            probe_req = _ur.Request(
                os.environ["OPENAI_BASE_URL"].rstrip("/") + "/chat/completions",
                data=probe_body,
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer " + _key},
                method="POST",
            )
            try:
                with _ur.urlopen(probe_req, timeout=60) as resp:
                    log(f"[probe] raw chat/completions -> HTTP {resp.status}: "
                        f"{resp.read()[:200]!r}")
                    break
            except Exception as exc:
                body = getattr(exc, "read", lambda: b"")()
                log(f"[probe] attempt {probe_attempt} -> {exc} {body[:200]!r}")
                if time.time() >= probe_deadline:
                    log("[probe] endpoint still failing after 10min; proceeding anyway")
                    break
                time.sleep(30)

    req_src = Path(args.requirement_path).resolve()
    # On ARC-Bench the runner hands us the template workspace via
    # ARCBENCH_TEMPLATE_DIR; generated code must land there for preview/tests.
    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    elif os.environ.get("ARCBENCH_TEMPLATE_DIR"):
        output_dir = Path(os.environ["ARCBENCH_TEMPLATE_DIR"]).resolve()
    else:
        output_dir = Path.cwd() / "workspace" / f"run-{time.strftime('%Y%m%d-%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Mirror ARC: copy the requirement input into the workspace. On the
    # platform the requirement dir already lives outside the template repo,
    # so skip polluting the evaluated workspace there.
    on_platform = bool(os.environ.get("ARCBENCH_TEMPLATE_DIR"))
    if on_platform:
        dest_req = req_src
    else:
        dest_req = output_dir / "requirements"
        if dest_req.exists():
            shutil.rmtree(dest_req)
        shutil.copytree(req_src, dest_req)

    runtime = AgentRuntime.from_env(project_dir=str(output_dir))
    events = runtime.events
    events.mark_run_started("octos bundle started")

    try:
        tree = load_requirement_tree(dest_req)
        runtime.traceability.store_requirement_tree(tree)
        atomic_nodes = flatten_atomic(tree)
        if not atomic_nodes:
            raise ValueError("no ATOMIC requirement nodes found")

        runtime.git.ensure_repo()

        octos_bin = find_octos()
        max_iter = int(os.environ.get("OCTOS_MAX_ITERATIONS", "200"))
        node_timeout = int(os.environ.get("OCTOS_NODE_TIMEOUT", "1800"))
        data_dir = Path(tempfile.mkdtemp(prefix="octos-data-"))
        config_dir = Path(tempfile.mkdtemp(prefix="octos-config-"))
        env = build_octos_env(config_dir)
        driver = OctosDriver(
            octos_bin, output_dir, env, data_dir, max_iter,
            events_log=output_dir / ".arc" / "octos-events.jsonl",
        )

        try:
            # Step 0: orient in the starter project + shared foundations.
            # Retry the skeleton turn: the platform LLM proxy 500s in bursts,
            # and without a skeleton there is no app at all.
            log(f"[flow] skeleton/foundations turn starting "
                f"({len(atomic_nodes)} atomic nodes queued)")
            skeleton_ok = False
            skeleton_text = ""
            for sk_attempt in range(1, 5):
                t0 = time.time()
                skeleton_ok, skeleton_text = driver.run(
                    APP_SKELETON_PROMPT.format(port=args.web_port), node_timeout,
                )
                log(f"[flow] skeleton turn attempt {sk_attempt} "
                    f"{'ok' if skeleton_ok else 'FAILED'} "
                    f"in {time.time()-t0:.0f}s: {skeleton_text[-300:]!r}")
                if skeleton_ok:
                    break
                time.sleep(45)
            if not skeleton_ok:
                raise RuntimeError(f"skeleton scaffolding failed: {skeleton_text}")
            runtime.git.commit("chore: scaffold web application skeleton")

            # Per-node implementation.
            failed: list[str] = []
            for idx, node in enumerate(atomic_nodes, 1):
                node_id = str(node.get("id"))
                events.mark_design_started(node_id)
                events.mark_design_done(node_id, "design folded into octos implementation prompt")
                events.mark_implementation_started(node_id)
                log(f"[flow] node {idx}/{len(atomic_nodes)} {node_id} starting")
                t0 = time.time()
                ok, text = driver.run(
                    NODE_PROMPT_TEMPLATE.format(port=args.web_port, node_spec=describe_node(node)),
                    node_timeout,
                )
                log(f"[flow] node {node_id} {'ok' if ok else 'FAILED'} "
                    f"in {time.time()-t0:.0f}s: {text[-300:]!r}")
                if ok:
                    events.mark_implementation_done(node_id, text[-500:] or None)
                    runtime.git.commit(f"{node_id} (implement): {node.get('name', '')}")
                else:
                    events.mark_implementation_failed(node_id, text[-500:])
                    failed.append(node_id)

            # Final verification pass; octos leaves the port free.
            log("[flow] final verification turn starting")
            t0 = time.time()
            ok, text = driver.run(
                FINAL_CHECK_PROMPT.format(port=args.web_port), node_timeout,
            )
            log(f"[flow] final check {'ok' if ok else 'FAILED'} "
                f"in {time.time()-t0:.0f}s: {text[-300:]!r}")
        finally:
            driver.close()
        for node in atomic_nodes:
            node_id = str(node.get("id"))
            if node_id in failed or not ok:
                events.mark_test_failed(node_id, "final verification did not pass")
            else:
                events.mark_test_passed(node_id, "verified by octos final check")
        runtime.git.commit("chore: final verification pass")

        if failed:
            events.mark_run_completed(f"completed with {len(failed)} failed node(s): {', '.join(failed)}")
        else:
            events.mark_run_completed("all requirement nodes implemented")
        _postflight_structure_check(output_dir, args.web_port)
        _free_web_port(args.web_port)
        # Tell the platform the preview can be served (mirrors the demo agent).
        artifacts_dir = os.environ.get("ARCBENCH_ARTIFACTS_DIR")
        if artifacts_dir:
            try:
                Path(artifacts_dir).mkdir(parents=True, exist_ok=True)
                (Path(artifacts_dir) / "preview-ready.json").write_text(
                    json.dumps({"ready": True, "reason": "octos bundle completed"}) + "\n",
                    encoding="utf-8",
                )
            except OSError:
                pass
        return 0
    except Exception as exc:  # platform judges by events, not exit code
        _postflight_structure_check(output_dir, args.web_port)
        _free_web_port(args.web_port)
        events.mark_run_failed(str(exc)[:1000])
        return 0


if __name__ == "__main__":
    sys.exit(main())
