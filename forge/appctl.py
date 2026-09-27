"""Build, syntax-check, start and smoke-test the generated application."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


class App:
    def __init__(self, root: Path, port: int = 3100, log=print) -> None:
        self.root = Path(root)
        self.port = port
        self.proc: subprocess.Popen | None = None
        self.log = log
        self.data_dir = Path(tempfile.mkdtemp(prefix="forge-data-"))
        self.log_path = self.root / ".arc" / "forge" / "server.log"

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def build(self) -> tuple[bool, str]:
        r = subprocess.run(["node", "build.js"], cwd=self.root / "frontend", capture_output=True, text=True, timeout=120)
        return r.returncode == 0, (r.stdout + r.stderr)[-3000:]

    def syntax_errors(self) -> list[str]:
        errors = []
        tmp = Path(tempfile.mkdtemp(prefix="forge-syntax-"))
        try:
            for base, esm in (("backend", False), ("frontend/src", True)):
                for p in sorted((self.root / base).rglob("*.js")):
                    if any(part in ("node_modules", "data", "dist") for part in p.parts):
                        continue
                    target = p
                    if esm:
                        target = tmp / (p.stem + f"_{abs(hash(str(p)))}.mjs")
                        shutil.copyfile(p, target)
                    r = subprocess.run(["node", "--check", str(target)], capture_output=True, text=True, timeout=30)
                    if r.returncode != 0:
                        msg = (r.stderr or r.stdout).replace(str(target), str(p.relative_to(self.root)))
                        errors.append(f"{p.relative_to(self.root)}:\n{msg.strip()[-1200:]}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return errors

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except Exception:
                self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except Exception:
                    pass
        self.proc = None

    def start(self, fresh: bool = True) -> tuple[bool, str]:
        self.stop()
        if fresh:
            shutil.rmtree(self.data_dir, ignore_errors=True)
            self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        logf = open(self.log_path, "w")
        env = dict(os.environ, PORT=str(self.port), HOST="127.0.0.1", DATA_DIR=str(self.data_dir))
        for k in ("OPENAI_API_KEY", "VISUAL_API_KEY"):
            env.pop(k, None)
        self.proc = subprocess.Popen(["node", "server.js"], cwd=self.root / "backend", stdout=logf, stderr=subprocess.STDOUT,
                                     env=env, start_new_session=True)
        deadline = time.time() + 25
        while time.time() < deadline:
            if self.proc.poll() is not None:
                return False, "backend exited during startup:\n" + self.server_log()
            try:
                with urllib.request.urlopen(self.base_url + "/api/health", timeout=2) as r:
                    if r.status == 200:
                        return True, ""
            except Exception:
                time.sleep(0.3)
        return False, "backend did not answer /api/health within 25s:\n" + self.server_log()

    def server_log(self, n: int = 4000) -> str:
        try:
            return self.log_path.read_text(errors="replace")[-n:]
        except Exception:
            return ""

    def browser_smoke(self, paths: list[str] | None = None) -> list[str]:
        """Load pages in Chromium and report module/runtime errors."""
        paths = paths or ["/"]
        out = Path(tempfile.mktemp(suffix=".json"))
        r = subprocess.run([sys.executable, str(HERE / "smoke.py"), self.base_url, str(out), *paths],
                           capture_output=True, text=True, timeout=120)
        if not out.exists():
            return [f"smoke runner failed: {(r.stderr or r.stdout)[-1500:]}"]
        data = json.loads(out.read_text())
        out.unlink(missing_ok=True)
        return data.get("errors", [])

    def run_tests(self, files: list[Path], timeout: int = 900) -> list[dict]:
        out = Path(tempfile.mktemp(suffix=".json"))
        try:
            subprocess.run([sys.executable, str(HERE / "testkit.py"), self.base_url, str(out), *map(str, files)],
                           capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return [{"file": str(f), "test": "<timeout>", "ok": False, "error": "test run timed out"} for f in files]
        if not out.exists():
            return [{"file": str(f), "test": "<crash>", "ok": False, "error": "test runner crashed"} for f in files]
        data = json.loads(out.read_text())
        out.unlink(missing_ok=True)
        return data
