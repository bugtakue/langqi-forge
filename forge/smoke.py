"""Load app pages in Chromium and collect JS errors. Usage: smoke.py <base_url> <out.json> <path>..."""

import json
import sys


def main() -> int:
    base, out, paths = sys.argv[1], sys.argv[2], sys.argv[3:]
    from playwright.sync_api import sync_playwright

    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror on {page.url}: {e}"[:600]))
        page.on("console", lambda m: errors.append(f"console error on {page.url}: {m.text}"[:600]) if m.type == "error" and "favicon" not in m.text else None)
        for path in paths:
            try:
                page.goto(base + path, wait_until="load", timeout=10000)
                page.wait_for_timeout(700)
                text = page.inner_text("body")
                if not text.strip():
                    errors.append(f"page {path} rendered no visible text")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"failed to load {path}: {exc}"[:600])
        browser.close()
    # ignore 4xx noise from expected unauthenticated API calls
    errors = [e for e in errors if "401" not in e and "Failed to load resource: the server responded with a status of 4" not in e]
    with open(out, "w") as f:
        json.dump({"errors": errors}, f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
