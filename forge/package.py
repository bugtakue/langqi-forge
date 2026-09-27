"""Build the ARC-Bench submission ZIP: main.py + requirements.txt + forge/ (whitelisted)."""

from __future__ import annotations

import argparse
import hashlib
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORGE = ROOT / "forge"

MAIN = '''#!/usr/bin/env python3
"""Langqi Forge: requirements -> planned, implemented, self-tested web application."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from forge.agent import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
'''

REQUIREMENTS = "pyyaml>=6.0,<7\narcbench-runtime==0.1.0\n"

SECRET_RE = re.compile(r"(sk-[A-Za-z0-9]{20,}|api[_-]?key\s*=\s*['\"][A-Za-z0-9]{16,})", re.I)


def members() -> list[tuple[str, bytes]]:
    out = [("main.py", MAIN.encode()), ("requirements.txt", REQUIREMENTS.encode())]
    for p in sorted(FORGE.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        if "__pycache__" in rel or rel.endswith((".pyc", ".DS_Store")) or "/tests/" in rel or rel.endswith("package.py"):
            continue
        data = p.read_bytes()
        if SECRET_RE.search(data.decode("utf-8", errors="ignore")):
            raise SystemExit(f"refusing to package possible secret in {rel}")
        out.append((rel, data))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(ROOT / "dist" / "langqi-forge-v2.zip"))
    args = ap.parse_args()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    items = members()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, data in items:
            info = zipfile.ZipInfo(rel, date_time=(2026, 9, 27, 0, 0, 0))
            info.external_attr = 0o644 << 16
            z.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"{out} {len(items)} files sha256={digest}")
    for rel, data in items:
        print(f"  {rel} {len(data)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
