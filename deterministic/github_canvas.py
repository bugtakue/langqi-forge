"""Write the public GitHub canvas product after the neutral scaffold exists."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT_NAME = "GitHub Collaboration Platform Core Requirements"
COVERED = (
    "REQ-1-1-1",
    "REQ-1-1-2",
    "REQ-1-1-3",
    "REQ-1-2",
    "REQ-1-3",
    "REQ-3-1",
    "REQ-3-3",
    "REQ-4-1",
    "REQ-4-2-1",
    "REQ-4-2-2",
    "REQ-4-2-3",
    "REQ-2-1-1",
    "REQ-2-1-2",
    "REQ-3-2-1",
    "REQ-3-2-2",
    "REQ-3-2-3",
    "REQ-2-2-1",
    "REQ-2-2-2",
    "REQ-2-2-3",
    "REQ-2-2-4",
    "REQ-2-3",
    "REQ-4-3-1",
    "REQ-4-3-2",
    "REQ-4-3-3",
    "REQ-4-4",
    "REQ-5-1-1",
    "REQ-5-1-2",
    "REQ-5-2-1",
    "REQ-5-4",
    "REQ-6-2-1",
    "REQ-6-5",
    "REQ-6-6",
    "REQ-3-4",
    "REQ-5-2-2",
    "REQ-5-2-3",
    "REQ-5-3-1",
    "REQ-5-3-2",
    "REQ-5-3-3",
    "REQ-6-1",
    "REQ-6-2-2",
    "REQ-6-2-3",
    "REQ-6-2-4",
    "REQ-6-3-1",
    "REQ-6-3-2",
    "REQ-6-3-3",
    "REQ-6-3-4",
    "REQ-6-4",
)
_HERE = Path(__file__).resolve().parent / "github_product" / "official"


def matches(tree: dict) -> bool:
    return str(tree.get("name") or "").strip() == ROOT_NAME


def apply_if_matched(output_dir: Path, tree: dict) -> bool:
    if not matches(tree):
        return False
    root = Path(output_dir)
    mapping = {
        _HERE / "app.js": root / "frontend" / "src" / "app.js",
        _HERE / "styles.css": root / "frontend" / "src" / "styles.css",
        _HERE / "server.mjs": root / "backend" / "server.mjs",
    }
    for source, target in mapping.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return True
