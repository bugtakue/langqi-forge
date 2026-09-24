"""Bounded private copies for checks that execute generated application code."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


IGNORED_PARTS = {"node_modules", ".git", ".arc", ".cache", "coverage"}
MAX_COPY_FILES = 5_000
MAX_COPY_BYTES = 100_000_000


def validate_app_project(
    root: Path, *, components: tuple[str, ...] = ("frontend", "backend")
) -> None:
    """Reject linked, special, or oversized app files before copying them."""

    file_count = 0
    total_bytes = 0
    for component in components:
        directory = root / component
        if directory.is_symlink() or not directory.is_dir():
            raise RuntimeError(
                f"isolated app check requires a regular {component}/ directory"
            )
        for current, directories, files in os.walk(directory, followlinks=False):
            directories[:] = [name for name in directories if name not in IGNORED_PARTS]
            for name in directories:
                path = Path(current) / name
                if path.is_symlink() or not path.is_dir():
                    raise RuntimeError("isolated app check cannot stage a linked directory")
            for name in files:
                if name in IGNORED_PARTS:
                    continue
                path = Path(current) / name
                if path.is_symlink() or not path.is_file():
                    raise RuntimeError("isolated app check cannot stage a linked or special file")
                file_count += 1
                total_bytes += path.stat().st_size
                if file_count > MAX_COPY_FILES or total_bytes > MAX_COPY_BYTES:
                    raise RuntimeError("application exceeds isolation copy limit")


def stage_app_project(
    source: Path, target: Path, *, components: tuple[str, ...] = ("frontend", "backend")
) -> None:
    """Copy only generated app files, never sharing persistent state or links."""

    validate_app_project(source, components=components)
    for component in components:
        shutil.copytree(
            source / component,
            target / component,
            symlinks=True,
            ignore=shutil.ignore_patterns(*IGNORED_PARTS),
        )
    # A source path changing between preflight and copy must still fail closed.
    validate_app_project(target, components=components)
