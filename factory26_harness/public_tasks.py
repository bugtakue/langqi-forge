from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


TEST_PATTERN = re.compile(r"^\s*test(?:\.\w+)?\s*\(", re.MULTILINE)


def _fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"user-agent": "factory26-harness/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object from {url}")
    return payload


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _safe_test_path(root: Path, relative: str) -> Path:
    candidate = Path(str(relative))
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ValueError(f"unsafe public test path: {relative}")
    resolved = (root / candidate).resolve()
    if root.resolve() not in resolved.parents:
        raise ValueError(f"public test path escapes bundle: {relative}")
    return resolved


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def sync_public_task(
    task_id: str,
    destination_root: Path,
    *,
    base_url: str = "http://arc-bench.com",
    catalog: str = "playground",
) -> dict[str, Any]:
    normalized_id = str(task_id).strip()
    if not normalized_id or not re.fullmatch(r"[A-Za-z0-9_-]+", normalized_id):
        raise ValueError(f"invalid task id: {task_id}")
    query = urllib.parse.urlencode({"catalog": catalog})
    prefix = base_url.rstrip("/") + "/api/requirements/" + urllib.parse.quote(normalized_id)
    detail_url = f"{prefix}?{query}"
    tests_url = f"{prefix}/tests?{query}"
    detail = _fetch_json(detail_url)
    tests = _fetch_json(tests_url)
    task_root = destination_root.resolve() / normalized_id
    requirements_yaml = str(detail.get("requirements_yaml") or "")
    if not requirements_yaml.strip():
        raise ValueError(f"task {normalized_id} has no requirements_yaml")
    requirements_markdown = str(detail.get("requirements_markdown") or "")
    prerequisites_markdown = str(detail.get("prerequisites_markdown") or "")
    _atomic_write(task_root / "requirements" / "requirements.yaml", requirements_yaml)
    _atomic_write(task_root / "requirements" / "README.md", requirements_markdown)
    _atomic_write(task_root / "requirements" / "PREREQUISITES.md", prerequisites_markdown)

    file_hashes: dict[str, str] = {}
    observed_test_count = 0
    files = tests.get("files") or []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        relative = str(entry.get("path") or "")
        content = str(entry.get("content") or "")
        path = _safe_test_path(task_root / "tests", relative)
        _atomic_write(path, content)
        file_hashes[relative] = _sha256(content)
        observed_test_count += len(TEST_PATTERN.findall(content))

    expected_test_count = int(detail.get("total_tests") or 0)
    if expected_test_count and observed_test_count != expected_test_count:
        raise ValueError(
            f"task {normalized_id} test count mismatch: expected {expected_test_count}, observed {observed_test_count}"
        )
    manifest = {
        "version": 1,
        "task_id": normalized_id,
        "title": str(detail.get("title") or ""),
        "catalog": catalog,
        "source": {"detail_url": detail_url, "tests_url": tests_url},
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "module_count": int(detail.get("module_count") or 0),
        "expected_test_count": expected_test_count,
        "observed_test_count": observed_test_count,
        "requirements_sha256": _sha256(requirements_yaml),
        "test_files": dict(sorted(file_hashes.items())),
    }
    _atomic_write(task_root / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize public ARC-Bench task packages")
    parser.add_argument("tasks", nargs="+", help="Task ids, e.g. github sheet")
    parser.add_argument("--output", type=Path, default=Path(".cache/public-tasks"))
    parser.add_argument("--base-url", default="http://arc-bench.com")
    parser.add_argument("--catalog", default="playground")
    args = parser.parse_args()
    for task_id in args.tasks:
        manifest = sync_public_task(
            task_id,
            args.output,
            base_url=args.base_url,
            catalog=args.catalog,
        )
        print(
            f"{manifest['task_id']}: {manifest['module_count']} modules, "
            f"{manifest['observed_test_count']} tests"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
