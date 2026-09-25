"""Offline regressions for delivering observations across both compaction paths."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory26_harness.agent import CodingAgent, _context_characters
from factory26_harness.checks import CheckResult
from factory26_harness.model import ModelReply
from factory26_harness.trace import ProductionTrace
from factory26_harness.workspace_tools import WorkspaceTools


DEFAULT_CONTEXT_CHARS = 96_000


def _call(identity, name, **arguments):
    return {"id": identity, "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments),
    }}


def _reply(calls, *, content="", reasoning="opaque provider continuation"):
    return ModelReply(
        content=content, tool_calls=tuple(calls),
        raw_message={"role": "assistant", "content": content,
                     "tool_calls": calls, "reasoning_content": reasoning},
        prompt_tokens=0, completion_tokens=0, response_id="offline-fixture",
        finish_reason="tool_calls",
    )


def _result_message(identity, result):
    return {"role": "tool", "tool_call_id": identity,
            "content": json.dumps(result, ensure_ascii=False, sort_keys=True)}


class _NextRequestCaptured(Exception):
    pass


class _ScriptedReplies:
    """Capture immutable requests; never construct a client or call a service."""

    def __init__(self, replies):
        self.script = replies
        self.requests = []
        self.emitted = []

    def complete(self, messages, _schemas):
        self.requests.append(copy.deepcopy(messages))
        index = len(self.emitted)
        if index == len(self.script):
            raise _NextRequestCaptured()
        item = self.script[index]
        response = item(messages) if callable(item) else item
        self.emitted.append(response)
        return response


class CompactionProtocolTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.trace = ProductionTrace(self.root / ".arc/trace.jsonl")
        self.tools = WorkspaceTools(self.root, self.trace, 33143)
        self.checks = [CheckResult("fixture", True, "offline validation", (), 0)]
        validation = patch(
            "factory26_harness.workspace_tools.run_quick_checks",
            return_value=self.checks,
        )
        self.validation = validation.start()
        self.addCleanup(validation.stop)

    def _source(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def _events(self, name):
        return [row["payload"] for row in (
            json.loads(line) for line in self.trace.path.read_text().splitlines()
        ) if row["event"] == name]

    def _capture(self, replies):
        scripted = _ScriptedReplies(replies)
        agent = CodingAgent(scripted, self.tools, self.trace, max_turns=len(replies) + 1)
        # Exercise the production default even if a developer's shell overrides it.
        agent.maximum_context_characters = DEFAULT_CONTEXT_CHARS
        with self.assertRaises(_NextRequestCaptured):
            agent._run("Offline compaction protocol fixture",
                       stage="implementation", requirement_ids=[])
        return scripted

    def _assert_paired(self, messages):
        pending = set()
        seen = set()
        for message in messages:
            if message["role"] == "tool":
                identity = message["tool_call_id"]
                self.assertIn(identity, pending, f"orphan tool result: {identity}")
                pending.remove(identity)
                continue
            self.assertFalse(pending, f"tool results missing before next message: {pending}")
            if message["role"] == "assistant":
                for call in message.get("tool_calls", []):
                    self.assertNotIn(call["id"], seen, "duplicate tool call")
                    seen.add(call["id"])
                    pending.add(call["id"])
        self.assertFalse(pending, f"unanswered tool calls: {pending}")

    def _assert_delivered(self, scripted, read_calls, reasoning):
        for request in scripted.requests:
            self._assert_paired(request)
        next_request = scripted.requests[-1]
        results = {m["tool_call_id"]: m for m in next_request if m["role"] == "tool"}
        calls = {c["id"]: (c, m) for m in next_request if m["role"] == "assistant"
                 for c in m.get("tool_calls", [])}
        executed = [c for response in scripted.emitted for c in response.tool_calls]
        recorded = self._events("tool_result")
        self.assertEqual(len(executed), len(recorded))
        expected = {c["id"]: row["result"] for c, row in zip(executed, recorded)}
        for call in read_calls:
            identity = call["id"]
            self.assertIn(identity, results, f"fresh read not delivered: {identity}")
            self.assertEqual(calls[identity][0], call)
            self.assertEqual(calls[identity][1]["reasoning_content"], reasoning)
            self.assertTrue(expected[identity]["ok"])
            # Exact result equality checks the whole body, SHA and page cursors,
            # not merely a marker that could survive in an optional snapshot.
            self.assertEqual(json.loads(results[identity]["content"]), expected[identity])

    def test_acceptance_compaction_delivers_just_read_source(self):
        self._source("frontend/unmodified.js", 'export const marker = "UNSEEN_ACCEPTANCE";\n')
        read = _call("fresh-read", "read_file", path="frontend/unmodified.js")
        reasoning = "acceptance continuation\nopaque field"

        def validate_after_read(messages):
            calls = [read, _call("validate", "run_validation", scope="quick")]
            predicted_results = [
                _result_message("fresh-read", self.tools._tool_read_file({
                    "path": "frontend/unmodified.js",
                })),
                _result_message("validate", {
                    "ok": True, "checks": [check.as_dict() for check in self.checks],
                    "validated_change_revision": 1, "current_changes_validated": True,
                }),
            ]
            base = _reply(calls, reasoning=reasoning)
            # Only adding the audit should cross 96K; rolling compaction must
            # not erase the distinction between the two compaction branches.
            padding = 95_500 - _context_characters(messages + [base.raw_message] + predicted_results)
            self.assertGreater(padding, 0)
            return _reply(calls, content="P" * padding, reasoning=reasoning)

        scripted = self._capture([
            _reply([_call("create", "write_file", path="backend/edited.js",
                          content="export const version = 1;\n")]),
            validate_after_read,
        ])
        events = self._events("agent_context_compacted")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["reason"], "acceptance_audit_context_limit")
        self.assertEqual(events[0]["before_characters"], 95_500)
        self.validation.assert_called_once()
        self._assert_delivered(scripted, [read], reasoning)

    def test_audit_invalidation_keeps_current_call_and_result_pairs(self):
        original = "export const version = 1;\n"
        self._source("frontend/unmodified.js", 'export const marker = "UNSEEN_REPAIR";\n')
        read = _call("repair-read", "read_file", path="frontend/unmodified.js")
        reasoning = "repair continuation\nopaque field"
        scripted = self._capture([
            _reply([_call("create", "write_file", path="backend/edited.js", content=original),
                    _call("validate", "run_validation", scope="quick")]),
            _reply([
                _call("rewrite", "write_file", path="backend/edited.js",
                      content="/*" + "X" * 96_000 + "*/\nexport const version = 2;\n",
                      expected_sha256=hashlib.sha256(original.encode()).hexdigest()),
                read,
            ], reasoning=reasoning),
        ])
        self.assertEqual(len(self._events("agent_acceptance_audit_invalidated")), 1)
        self.assertTrue(self._events("agent_context_compacted"))
        self.validation.assert_called_once()
        self._assert_delivered(scripted, [read], reasoning)

    def test_rolling_compaction_preserves_multiple_reads_and_reasoning(self):
        self._source("frontend/a.js", 'export const a = "READ_A";\n')
        self._source("frontend/b.js", 'export const b = "READ_B";\n')
        self.tools.register_requirement_specs({"R": "The complete assigned specification."})
        reads = [
            _call("read-a", "read_file", path="frontend/a.js"),
            _call("read-spec", "read_requirement_spec", requirement_id="R", start_char=0),
            _call("read-b", "read_file", path="frontend/b.js"),
        ]
        reasoning = 'opaque multi-read continuation\n"中文"'
        scripted = self._capture([_reply([
            *reads,
            _call("create", "write_file", path="backend/edited.js",
                  content="/*" + "X" * 96_000 + "*/\n"),
        ], reasoning=reasoning)])
        events = self._events("agent_context_compacted")
        self.assertEqual(len(events), 1)
        self.assertFalse(events[0]["retained_current_turn"])
        self.assertLessEqual(_context_characters(scripted.requests[-1]), DEFAULT_CONTEXT_CHARS)
        self.assertTrue(self.tools.requirement_specs_complete)
        self.validation.assert_not_called()
        self._assert_delivered(scripted, reads, reasoning)

    def test_acceptance_delivers_new_observations_even_above_soft_limit(self):
        reads = []
        for index in range(7):
            path = f"frontend/escaped-{index}.js"
            # Each direct result fits 12K, but JSON-encoding these escaped
            # results inside messages makes the seven observations exceed 96K.
            self._source(path, "//" + "\\" * 4_000 + f" UNIQUE_{index}\n")
            reads.append(_call(f"escaped-{index}", "read_file", path=path))
        reasoning = "soft overflow continuation\nopaque field"
        scripted = self._capture([
            _reply([_call("create", "write_file", path="backend/edited.js",
                          content="export const ready = true;\n")]),
            _reply([*reads, _call("validate", "run_validation", scope="quick")],
                   reasoning=reasoning),
        ])
        events = self._events("agent_context_compacted")
        self.assertTrue(any(e.get("reason") == "acceptance_audit_context_limit" for e in events))
        self.validation.assert_called_once()
        self._assert_delivered(scripted, reads, reasoning)
        next_request = scripted.requests[-1]
        read_ids = {call["id"] for call in reads}
        observations = [m for m in next_request if (
            m["role"] == "tool" and m["tool_call_id"] in read_ids
        ) or (m["role"] == "assistant" and any(
            c["id"] in read_ids for c in m.get("tool_calls", [])
        ))]
        self.assertGreater(_context_characters(observations), DEFAULT_CONTEXT_CHARS)
        self.assertGreater(_context_characters(next_request), DEFAULT_CONTEXT_CHARS)
        audit = self._events("agent_acceptance_audit_requested")[-1]
        self.assertLessEqual(sum(row["included_bytes"] for row in audit["snapshot"]), 12_000)


if __name__ == "__main__":
    unittest.main()
