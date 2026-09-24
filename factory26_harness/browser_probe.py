"""Bounded, task-neutral browser inspection of the generated local app.

The model supplies semantic actions, not JavaScript, shell, hidden tests, or a
remote URL. The browser can contact only this run's loopback application.
"""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .checks import _npm_install, _port_available, _safe_environment, _wait_for_health
from .isolation import stage_app_project


MAX_STEPS = 8
MAX_ASSERTIONS = 4
MAX_TEXT_CHARS = 2800
OBSERVATION_SETTLE_SECONDS = 2.0
ALLOWED_ACTIONS = {"click", "fill", "press", "select", "check", "reload", "navigate"}


def _bounded_text(value: Any, *, maximum: int = 200) -> str:
    text = str(value or "")
    if not text or len(text) > maximum or any(ord(char) < 32 for char in text):
        raise ValueError(f"browser step text must contain 1-{maximum} printable characters")
    return text


def _local_path(value: Any) -> str:
    path = _bounded_text(value, maximum=500)
    parsed = urlsplit(path)
    if (
        not path.startswith("/")
        or path.startswith("//")
        or "\\" in path
        or parsed.scheme
        or parsed.netloc
        or parsed.fragment
    ):
        raise ValueError("browser navigation must use a local path beginning with /")
    return path


def validate_steps(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > MAX_STEPS:
        raise ValueError(f"browser steps must be an array of at most {MAX_STEPS} actions")
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(value, 1):
        if not isinstance(raw, dict) or str(raw.get("action") or "") not in ALLOWED_ACTIONS:
            raise ValueError(f"browser step {index} has an unsupported action")
        action = str(raw["action"])
        step: dict[str, Any] = {"action": action}
        if action == "navigate":
            step["path"] = _local_path(raw.get("path"))
        elif action != "reload":
            locators = [key for key in ("role", "label", "text") if raw.get(key)]
            if len(locators) != 1:
                raise ValueError(f"browser step {index} needs exactly one semantic locator")
            kind = locators[0]
            if kind == "role":
                step["role"] = _bounded_text(raw["role"], maximum=40)
                step["name"] = _bounded_text(raw.get("name"), maximum=200)
            else:
                if kind == "text" and action not in {"click", "press"}:
                    raise ValueError("text locator is only supported for click and press")
                step[kind] = _bounded_text(raw[kind])
            offset = raw.get("index", 0)
            if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 19:
                raise ValueError("browser locator index must be an integer from 0 to 19")
            step["index"] = offset
            if action in {"fill", "press", "select"}:
                step["value"] = _bounded_text(raw.get("value"), maximum=500)
            if action == "select":
                option_by = str(raw.get("option_by") or "label")
                if option_by not in {"label", "value"}:
                    raise ValueError("select option_by must be label or value")
                step["option_by"] = option_by
        for key in ("expect_text", "expect_absent"):
            values = raw.get(key) or []
            if not isinstance(values, list) or len(values) > MAX_ASSERTIONS:
                raise ValueError(f"{key} must contain at most {MAX_ASSERTIONS} strings")
            step[key] = [_bounded_text(item, maximum=200) for item in values]
        result.append(step)
    return result


def _locator(page: Any, step: dict[str, Any]) -> Any:
    if "role" in step:
        selection = page.get_by_role(step["role"], name=step["name"], exact=True)
    elif "label" in step:
        selection = page.get_by_label(step["label"], exact=True)
    else:
        selection = page.get_by_text(step["text"], exact=True)
    return selection.nth(step.get("index", 0))


def _controls(page: Any) -> list[dict[str, str]]:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('button,input,select,textarea,a[href]'))
          .slice(0, 40).map((element) => ({
            tag: element.tagName.toLowerCase(),
            role: element.getAttribute('role') || '',
            name: (element.getAttribute('aria-label') ||
                   (element.labels && element.labels[0] && element.labels[0].innerText) ||
                   element.innerText || element.getAttribute('placeholder') || '').trim().slice(0, 120),
            disabled: Boolean(element.disabled),
          }))"""
    )


def _page_observation(page: Any, *, expected: list[str], absent: list[str]) -> dict[str, Any]:
    body = page.locator("body").inner_text(timeout=4000)
    missing = [item for item in expected if item not in body]
    unexpected = [item for item in absent if item in body]
    current = urlsplit(page.url)
    return {
        "path": current.path + (f"?{current.query}" if current.query else ""),
        "visible_text": body[:MAX_TEXT_CHARS],
        "visible_text_truncated": len(body) > MAX_TEXT_CHARS,
        "missing_text": missing,
        "unexpected_text": unexpected,
        "controls": _controls(page),
    }


def _settled_observation(
    page: Any,
    *,
    expected: list[str],
    absent: list[str],
    require_visible_text: bool = False,
) -> dict[str, Any]:
    """Wait briefly for async DOM updates before judging a local user action."""

    deadline = time.monotonic() + OBSERVATION_SETTLE_SECONDS
    while True:
        observed = _page_observation(page, expected=expected, absent=absent)
        if (
            not observed["missing_text"]
            and not observed["unexpected_text"]
            and (not require_visible_text or observed["visible_text"].strip())
        ):
            return observed
        if time.monotonic() >= deadline:
            return observed
        page.wait_for_timeout(100)


def _perform(page: Any, step: dict[str, Any], base_url: str) -> None:
    action = step["action"]
    if action == "navigate":
        page.goto(base_url + step["path"], wait_until="domcontentloaded", timeout=10000)
    elif action == "reload":
        page.reload(wait_until="domcontentloaded", timeout=10000)
    else:
        target = _locator(page, step)
        if action == "click":
            target.click(timeout=5000)
        elif action == "fill":
            target.fill(step["value"], timeout=5000)
        elif action == "press":
            target.press(step["value"], timeout=5000)
        elif action == "select":
            target.select_option(**{step["option_by"]: step["value"]}, timeout=5000)
        elif action == "check":
            target.check(timeout=5000)
    page.wait_for_timeout(150)


def _stop_server(process: subprocess.Popen[Any]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def probe_local_app(root: Path, port: int, steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Exercise an isolated copy so self-tests cannot consume evaluator seed data."""

    validated = validate_steps(steps)
    root = root.resolve()
    if not (root / "frontend" / "dist" / "index.html").is_file():
        raise RuntimeError("frontend/dist/index.html is missing; run quick validation first")
    if not _port_available(port):
        raise RuntimeError(f"browser probe port {port} is already occupied")
    with tempfile.TemporaryDirectory(prefix="factory26-browser-probe-") as directory:
        isolated_root = Path(directory)
        stage_app_project(root, isolated_root)
        result = _probe_isolated_app(isolated_root, port, validated)
        return {**result, "workspace_isolated": True}


def _probe_isolated_app(root: Path, port: int, validated: list[dict[str, Any]]) -> dict[str, Any]:
    backend = root / "backend"
    install_rc, install_output, _ = _npm_install(backend)
    if install_rc != 0:
        raise RuntimeError(f"backend npm install failed: {install_output[-1000:]}")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Runner Playwright Python package is unavailable") from exc

    server_log = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")
    try:
        server = subprocess.Popen(
            ["npm", "start"],
            cwd=backend,
            env=_safe_environment(PORT=str(port)),
            stdout=server_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except BaseException:
        server_log.close()
        raise
    try:
        ready, summary = _wait_for_health(port, server, 30)
        if not ready:
            server_log.seek(0)
            raise RuntimeError(
                f"local app health check failed: {summary}; "
                f"server output: {server_log.read()[-2000:]}"
            )
        base_url = f"http://127.0.0.1:{port}"
        blocked_hosts: set[str] = set()
        page_errors: list[str] = []
        observations: list[dict[str, Any]] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            try:
                context = browser.new_context(service_workers="block")

                def local_only(route: Any) -> None:
                    request_url = urlsplit(route.request.url)
                    if (
                        request_url.scheme in {"http", "https"}
                        and request_url.hostname == "127.0.0.1"
                        and request_url.port == port
                    ):
                        route.continue_()
                    elif request_url.scheme in {"data", "blob"}:
                        route.continue_()
                    else:
                        blocked_hosts.add(request_url.hostname or request_url.scheme or "unknown")
                        route.abort()

                context.route("**/*", local_only)
                page = context.new_page()
                page.on("pageerror", lambda error: page_errors.append(str(error)[:500]))
                page.goto(base_url + "/", wait_until="domcontentloaded", timeout=10000)
                page.wait_for_timeout(150)
                initial = _settled_observation(
                    page, expected=[], absent=[], require_visible_text=True
                )
                observations.append({"action": "open", **initial})
                for step in validated:
                    _perform(page, step, base_url)
                    current = urlsplit(page.url)
                    if current.hostname != "127.0.0.1" or current.port != port:
                        raise RuntimeError("browser left the local generated application")
                    observed = _settled_observation(
                        page,
                        expected=step["expect_text"],
                        absent=step["expect_absent"],
                    )
                    observations.append({"action": step["action"], **observed})
                context.close()
            finally:
                browser.close()
        assertion_failures = [
            {"step": index, "missing": row["missing_text"], "unexpected": row["unexpected_text"]}
            for index, row in enumerate(observations)
            if row["missing_text"] or row["unexpected_text"]
        ]
        if not initial["visible_text"].strip():
            assertion_failures.append({"step": 0, "missing": ["visible application text"], "unexpected": []})
        return {
            "ok": not assertion_failures and not page_errors,
            "observations": observations,
            "assertion_failures": assertion_failures,
            "page_errors": page_errors[:10],
            "blocked_external_hosts": sorted(blocked_hosts)[:10],
            "behavioral_checks": len(validated),
            "behavioral_assertions": sum(
                len(step["expect_text"]) + len(step["expect_absent"])
                for step in validated
            ),
        }
    finally:
        _stop_server(server)
        server_log.close()
