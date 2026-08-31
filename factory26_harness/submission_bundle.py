from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


SOURCE_MANIFEST_NAME = "factory26-source.json"
SOURCE_MANIFEST_SCHEMA = "langqi-forge-submission-v1"
FIXED_ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)
ROOT_FILES = ("main.py", "requirements.txt")
PACKAGE_PREFIXES = ("arcbench_agent_runtime/", "factory26_harness/")
EXCLUDED_PARTS = frozenset({"__pycache__", ".git", ".venv", "dist"})
EXCLUDED_PACKAGE_FILES = frozenset(
    {
        "factory26_harness/evidence.py",
        "factory26_harness/feedback.py",
        "factory26_harness/judge_report.py",
        "factory26_harness/public_eval.py",
        "factory26_harness/public_fixtures.py",
        "factory26_harness/public_tasks.py",
        "factory26_harness/qualification.py",
        "factory26_harness/verify_evidence.py",
    }
)
SECRET_NAME_MARKERS = (
    ".env",
    "account.txt",
    "credentials",
    "api_key",
    "apikey",
    "secret",
    "token",
    ".pem",
    ".key",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git_output(source_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=source_root,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    ).stdout.strip()


def _source_revision(source_root: Path) -> str:
    revision = _git_output(source_root, "rev-parse", "HEAD")
    if len(revision) != 40 or any(
        character not in "0123456789abcdef" for character in revision
    ):
        raise RuntimeError("source revision is not a full lowercase Git commit hash")
    return revision


def _require_clean_source(source_root: Path) -> None:
    status = _git_output(
        source_root,
        "status",
        "--porcelain",
        "--untracked-files=normal",
    )
    if status:
        raise RuntimeError("refusing to package a dirty source tree")


def _safe_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"unsafe bundle path: {value}")
    if any(part in EXCLUDED_PARTS for part in path.parts):
        raise ValueError(f"excluded bundle path: {value}")
    lowered = value.lower()
    if any(marker in lowered for marker in SECRET_NAME_MARKERS):
        raise ValueError(
            f"secret-like path is forbidden in a submission bundle: {value}"
        )
    return path.as_posix()


def runtime_source_files(source_root: Path) -> tuple[str, ...]:
    selected: list[str] = []
    for relative in ROOT_FILES:
        if not (source_root / relative).is_file():
            raise FileNotFoundError(
                f"required submission file is missing: {relative}"
            )
        selected.append(relative)
    for prefix in PACKAGE_PREFIXES:
        package_root = source_root / prefix
        if not package_root.is_dir():
            raise FileNotFoundError(
                f"required submission package is missing: {prefix}"
            )
        for path in sorted(package_root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source_root).as_posix()
            if any(
                part in EXCLUDED_PARTS for part in PurePosixPath(relative).parts
            ):
                continue
            if relative in EXCLUDED_PACKAGE_FILES:
                continue
            if not (
                relative.endswith(".py")
                or relative.startswith("factory26_harness/templates/")
            ):
                continue
            selected.append(_safe_relative_path(relative))
    return tuple(sorted(set(selected)))


def _read_runtime_files(
    source_root: Path, relative_paths: tuple[str, ...]
) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    resolved_root = source_root.resolve()
    for relative in relative_paths:
        safe_relative = _safe_relative_path(relative)
        path = source_root / safe_relative
        if path.is_symlink():
            raise RuntimeError(
                f"symlinks are forbidden in a submission bundle: {safe_relative}"
            )
        resolved = path.resolve(strict=True)
        if resolved_root not in resolved.parents:
            raise RuntimeError(
                f"bundle source escapes repository root: {safe_relative}"
            )
        files[safe_relative] = resolved.read_bytes()
    return files


def source_manifest(revision: str, files: dict[str, bytes]) -> dict[str, Any]:
    file_entries = {
        path: {"sha256": _sha256_bytes(content), "size": len(content)}
        for path, content in sorted(files.items())
    }
    contract = {
        "schema": SOURCE_MANIFEST_SCHEMA,
        "source_revision": revision,
        "source_worktree_clean": True,
        "runtime": "python",
        "entrypoint": "main.py",
        "files": file_entries,
    }
    return {
        **contract,
        "contract_sha256": _sha256_bytes(
            _canonical_json(contract).encode("utf-8")
        ),
    }


def verify_source_manifest(source_root: Path) -> dict[str, Any]:
    manifest_path = source_root / SOURCE_MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("submission source manifest is unreadable") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != SOURCE_MANIFEST_SCHEMA
    ):
        raise RuntimeError("submission source manifest schema is invalid")
    contract = {
        key: manifest.get(key)
        for key in (
            "schema",
            "source_revision",
            "source_worktree_clean",
            "runtime",
            "entrypoint",
            "files",
        )
    }
    expected_contract_sha = _sha256_bytes(
        _canonical_json(contract).encode("utf-8")
    )
    if manifest.get("contract_sha256") != expected_contract_sha:
        raise RuntimeError("submission source manifest contract hash is invalid")
    revision = str(manifest.get("source_revision") or "")
    if len(revision) != 40 or any(
        character not in "0123456789abcdef" for character in revision
    ):
        raise RuntimeError("submission source revision is invalid")
    if manifest.get("source_worktree_clean") is not True:
        raise RuntimeError("submission source manifest is not marked clean")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise RuntimeError("submission source manifest has no files")
    discovered = {
        path.relative_to(source_root).as_posix()
        for path in source_root.rglob("*")
        if (path.is_file() or path.is_symlink())
        and not any(part == "__pycache__" for part in path.parts)
    }
    expected_paths = {str(path) for path in files} | {SOURCE_MANIFEST_NAME}
    if discovered != expected_paths:
        raise RuntimeError(
            "submission source file set does not match manifest: "
            f"missing={sorted(expected_paths - discovered)}, "
            f"unexpected={sorted(discovered - expected_paths)}"
        )
    for relative, expected in sorted(files.items()):
        safe_relative = _safe_relative_path(str(relative))
        if not isinstance(expected, dict):
            raise RuntimeError(f"invalid source manifest entry: {safe_relative}")
        path = source_root / safe_relative
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(
                f"submission source file is missing or unsafe: {safe_relative}"
            )
        content = path.read_bytes()
        if (
            expected.get("size") != len(content)
            or expected.get("sha256") != _sha256_bytes(content)
        ):
            raise RuntimeError(
                f"submission source file does not match manifest: {safe_relative}"
            )
    return manifest


def _zip_info(relative: str, *, executable: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(relative, FIXED_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    mode = 0o755 if executable else 0o644
    info.external_attr = (stat.S_IFREG | mode) << 16
    info.create_system = 3
    return info


def build_submission_bundle(
    source_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    output_path = output_path.expanduser().resolve()
    _require_clean_source(source_root)
    revision = _source_revision(source_root)
    relative_paths = runtime_source_files(source_root)
    files = _read_runtime_files(source_root, relative_paths)
    manifest = source_manifest(revision, files)
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_fd, temporary_name = tempfile.mkstemp(
        prefix=output_path.name + ".",
        suffix=".tmp",
        dir=output_path.parent,
    )
    os.close(temporary_fd)
    temporary_path = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for relative, content in sorted(files.items()):
                archive.writestr(
                    _zip_info(relative, executable=relative == "main.py"),
                    content,
                )
            archive.writestr(_zip_info(SOURCE_MANIFEST_NAME), manifest_bytes)
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return {
        "schema": SOURCE_MANIFEST_SCHEMA,
        "path": str(output_path),
        "sha256": _sha256_bytes(output_path.read_bytes()),
        "size": output_path.stat().st_size,
        "file_count": len(files) + 1,
        "source_revision": revision,
        "source_worktree_clean": True,
        "entrypoint": "main.py",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a minimal, deterministic, non-uploading Factory26 agent bundle"
        )
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dist/langqi-forge-agent.zip"),
    )
    args = parser.parse_args()
    result = build_submission_bundle(args.source_root, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
