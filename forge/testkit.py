"""Run model-written Python Playwright tests against a live app.

Usage: python testkit.py <base_url> <out.json> <test_file.py> [...]
Every `test_*` function receives (page, base_url) in a fresh browser context.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
import traceback
from pathlib import Path

ACTION_TIMEOUT_MS = 8000
TEST_BUDGET_S = 25.0


def main() -> int:
    base_url, out_path, files = sys.argv[1], sys.argv[2], sys.argv[3:]
    from playwright.sync_api import expect, sync_playwright

    expect.set_options(timeout=ACTION_TIMEOUT_MS)
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for file in files:
            name = Path(file).stem
            try:
                spec = importlib.util.spec_from_file_location(f"t_{name}", file)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            except Exception:
                results.append({"file": file, "test": "<import>", "ok": False,
                                "error": traceback.format_exc(limit=3)[-1500:], "seconds": 0})
                continue
            tests = [(k, v) for k, v in vars(mod).items() if k.startswith("test_") and callable(v)]
            for tname, fn in tests:
                ctx = browser.new_context(base_url=base_url, viewport={"width": 1280, "height": 900},
                                          permissions=["clipboard-read", "clipboard-write"])
                ctx.set_default_timeout(ACTION_TIMEOUT_MS)
                page = ctx.new_page()
                console: list[str] = []
                page.on("console", lambda m: console.append(f"{m.type}: {m.text}"[:300]) if m.type in ("error", "warning") else None)
                page.on("pageerror", lambda e: console.append(f"pageerror: {e}"[:300]))
                t0 = time.time()
                ok, err = True, ""
                try:
                    fn(page, base_url)
                    if time.time() - t0 > TEST_BUDGET_S:
                        ok, err = False, f"test exceeded {TEST_BUDGET_S}s budget"
                except Exception as exc:  # noqa: BLE001
                    ok = False
                    tb = traceback.extract_tb(exc.__traceback__)
                    loc = ""
                    for fr in tb:
                        if fr.filename == file:
                            loc = f"line {fr.lineno}: {fr.line}"
                    err = f"{type(exc).__name__}: {str(exc)[:1400]}\nat {loc}"
                    try:
                        err += f"\nURL at failure: {page.url}\nVisible text (truncated): " + page.inner_text("body")[:1200]
                    except Exception:
                        pass
                if console:
                    err += ("\nBrowser console:\n" + "\n".join(console[-8:])) if not ok else ""
                results.append({"file": file, "test": tname, "ok": ok, "error": err, "seconds": round(time.time() - t0, 2)})
                ctx.close()
        browser.close()
    Path(out_path).write_text(json.dumps(results, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
