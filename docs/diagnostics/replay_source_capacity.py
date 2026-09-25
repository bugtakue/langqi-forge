"""Offline capacity comparison, not a model/score replay.

Reads only the sealed generation trace and hash-matched generation sources.
Never reads business data from the scoring-time project download. Results use
redacted request messages, so report their size delta from the recorded count.
Not shipped in the competition bundle.
"""
import argparse
import hashlib
import json
import statistics
import tempfile
import zipfile
from pathlib import Path

from factory26_harness.agent import _context_characters, _fit_source_snapshot
from factory26_harness.trace import verify_trace_rows


def replay(base: Path, first: int, last: int) -> dict:
    with zipfile.ZipFile(base / "factory26-evidence.zip") as archive:
        rows = [json.loads(line) for line in archive.read("production-trace.jsonl").splitlines()]
    verify_trace_rows(rows, require_fully_sealed=True)
    results, unused = [], []
    with tempfile.TemporaryDirectory(prefix="factory26-sealed-replay.") as directory, \
            zipfile.ZipFile(base / "project-partial-20260925T1109.zip") as partial, \
            zipfile.ZipFile(base / "project-final-generation.zip") as final:
        root = Path(directory)
        for index, row in enumerate(rows):
            if row["event"] != "agent_context_compacted" or not first <= row["sequence"] <= last:
                continue
            request = None
            for following in rows[index + 1:]:
                if following["event"] in ("agent_session_started", "implementation_batch_finished"):
                    break
                if following["event"] == "model_request":
                    request = following
                    break
            if request is None:
                unused.append(row["sequence"])
                continue
            manifest = row["payload"]["source_snapshot"]
            paths = []
            for item in manifest:
                relative = Path(item["path"])
                if relative.parts[0] not in ("frontend", "backend") or ".." in relative.parts:
                    raise ValueError("unexpected generation source path")
                data = partial.read("template/" + item["path"])
                if hashlib.sha256(data).hexdigest() != item["sha256"]:
                    if relative.suffix not in (".js", ".mjs", ".css", ".html"):
                        raise ValueError("refusing scoring-time business data")
                    data = final.read("template/" + item["path"])
                if hashlib.sha256(data).hexdigest() != item["sha256"] or len(data) != item["bytes"]:
                    raise ValueError("source does not match sealed generation snapshot")
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                paths.append(item["path"])
            messages = request["payload"]["payload"]["messages"]
            marker, end = "<untrusted_current_sources>\n", "\n</untrusted_current_sources>"
            position = next(i for i, message in enumerate(messages) if marker in (message.get("content") or ""))
            prefix, tail = messages[position]["content"].split(marker, 1)
            _, suffix = tail.split(end, 1)

            def with_source(text):
                candidate = list(messages)
                candidate[position] = {**messages[position], "content": prefix + marker + text + end + suffix}
                return candidate

            budget = min(36_000, max(0, 96_000 - _context_characters(with_source("")) - 800))
            text, retained = _fit_source_snapshot(root, paths, maximum_bytes=budget,
                fits=lambda source: _context_characters(with_source(source)) <= 96_000)
            before = _context_characters(messages)
            results.append({
                "sequence": row["sequence"],
                "before_bytes": sum(item["included_bytes"] for item in manifest),
                "after_bytes": sum(item["included_bytes"] for item in retained),
                "before_characters": before,
                "after_characters": _context_characters(with_source(text)),
                "redacted_character_delta": before - row["payload"]["after_characters"],
                "large_complete_before": sum(not item["truncated"] and item["bytes"] > 10_000 for item in manifest),
                "large_complete_after": sum(not item["truncated"] and item["bytes"] > 10_000 for item in retained),
            })
    if not results:
        raise ValueError("no applicable rolling checkpoints")
    return {"checkpoints": results, "unused_checkpoints": unused, "summary": {
        "count": len(results),
        "median_byte_ratio": statistics.median(item["after_bytes"] / item["before_bytes"] for item in results),
        "improved": sum(item["after_bytes"] > item["before_bytes"] for item in results),
        "max_characters": max(item["after_characters"] for item in results),
        "redacted_character_delta_range": [min(item["redacted_character_delta"] for item in results),
                                           max(item["redacted_character_delta"] for item in results)],
        "model_calls": 0, "official_score_comparison": False,
    }}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_directory", type=Path)
    parser.add_argument("--first", type=int, required=True)
    parser.add_argument("--last", type=int, required=True)
    arguments = parser.parse_args()
    print(json.dumps(replay(arguments.evidence_directory, arguments.first, arguments.last), indent=2))
