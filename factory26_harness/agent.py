from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from .model import OpenAIChatClient
from .requirements import RequirementNode
from .trace import ProductionTrace
from .workspace_tools import WorkspaceTools


SYSTEM_PROMPT = """You are the implementation worker inside a scored ARC-Bench harness.
Your job is to EDIT the provided frontend/ and backend/ so the assigned requirements work end to end.

Hard rules:
- Use the tools to inspect and edit files. Do not merely describe code.
- Keep frontend/ buildable with `npm run build` and backend/ startable with `npm start` using PORT.
- Never start a server yourself; use run_validation, which uses a safe smoke port.
- Preserve `/api/health` and persistent backend state across refresh and process restart.
- Implement real behavior, not screenshots or hard-coded answers.
- Use visible labels, semantic buttons, `type="text"`, JavaScript validation messages, and real disabled states.
- Make the smallest coherent change. Do not rewrite unrelated working features.
- Hidden tests are unavailable. Generalize from the requirement rather than guessing test data.
- Call run_validation("quick") before finishing a feature batch.
When complete, return a short summary of files changed and any remaining risk.
"""


@dataclass(frozen=True)
class AgentRun:
    completed: bool
    summary: str
    changed_files: tuple[str, ...]
    turns: int


def _assistant_message(reply_message: dict[str, Any]) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": reply_message.get("content") or ""}
    if reply_message.get("tool_calls"):
        message["tool_calls"] = reply_message["tool_calls"]
    return message


class CodingAgent:
    def __init__(
        self,
        model: OpenAIChatClient,
        tools: WorkspaceTools,
        trace: ProductionTrace,
        max_turns: int = 14,
    ) -> None:
        self.model = model
        self.tools = tools
        self.trace = trace
        self.max_turns = max(2, max_turns)

    def implement(self, nodes: Iterable[RequirementNode], related_files: Iterable[str] = ()) -> AgentRun:
        nodes = list(nodes)
        requirement_text = "\n\n".join(node.compact_spec() for node in nodes)
        related = sorted({path for path in related_files if path})
        prompt = (
            "Implement this requirement batch now.\n\n"
            + requirement_text
            + ("\n\nPreviously observed related files:\n- " + "\n- ".join(related) if related else "")
        )
        return self._run(prompt, stage="implementation", requirement_ids=[node.req_id for node in nodes])

    def repair(self, failure_text: str, related_files: Iterable[str]) -> AgentRun:
        related = sorted({path for path in related_files if path})
        prompt = (
            "A deterministic validation failed. Find the root cause, edit only what is needed, then run full validation.\n\n"
            f"Failure:\n{failure_text[-6000:]}\n\n"
            + ("Likely related files:\n- " + "\n- ".join(related) if related else "Inspect the minimal relevant files first.")
        )
        return self._run(prompt, stage="repair", requirement_ids=[])

    def _run(self, prompt: str, *, stage: str, requirement_ids: list[str]) -> AgentRun:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        self.trace.record("agent_session_started", stage=stage, requirement_ids=requirement_ids, prompt=prompt)
        changed_before = set(self.tools.changed_files)
        final_summary = ""
        no_tool_turns = 0
        for turn in range(1, self.max_turns + 1):
            reply = self.model.complete(messages, self.tools.schemas())
            messages.append(_assistant_message(reply.raw_message))
            if not reply.tool_calls:
                final_summary = reply.content.strip()
                no_tool_turns += 1
                if self.tools.changed_files - changed_before or no_tool_turns >= 2:
                    changed = tuple(sorted(self.tools.changed_files - changed_before))
                    self.trace.record(
                        "agent_session_completed",
                        stage=stage,
                        requirement_ids=requirement_ids,
                        changed_files=changed,
                        summary=final_summary,
                    )
                    return AgentRun(bool(changed) or stage == "repair", final_summary, changed, turn)
                messages.append(
                    {
                        "role": "user",
                        "content": "You have not edited any file. Use the available tools and implement the requirement now.",
                    }
                )
                continue
            no_tool_turns = 0
            for call in reply.tool_calls:
                function = call.get("function") or {}
                name = str(function.get("name") or "")
                raw_arguments = function.get("arguments") or "{}"
                try:
                    arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else dict(raw_arguments)
                except (json.JSONDecodeError, TypeError, ValueError):
                    arguments = {}
                result = self.tools.execute(name, arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(call.get("id") or name),
                        "content": result,
                    }
                )
        changed = tuple(sorted(self.tools.changed_files - changed_before))
        self.trace.record(
            "agent_session_exhausted",
            stage=stage,
            requirement_ids=requirement_ids,
            changed_files=changed,
        )
        return AgentRun(False, final_summary or "maximum tool turns reached", changed, self.max_turns)
