from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .trace import ProductionTrace


@dataclass(frozen=True)
class ModelReply:
    content: str
    tool_calls: tuple[dict[str, Any], ...]
    raw_message: dict[str, Any]
    prompt_tokens: int
    completion_tokens: int


class OpenAIChatClient:
    def __init__(self, trace: ProductionTrace) -> None:
        self.api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.base_url = os.environ.get("OPENAI_BASE_URL", "").strip()
        self.model = os.environ.get("MODEL", "").strip()
        self.trace = trace
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        if not self.api_key or not self.base_url or not self.model:
            raise RuntimeError("OPENAI_API_KEY, OPENAI_BASE_URL and MODEL are required")

    @property
    def endpoint(self) -> str:
        normalized = self.base_url.rstrip("/")
        return normalized if normalized.endswith("/chat/completions") else normalized + "/chat/completions"

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelReply:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0,
            "max_tokens": int(os.environ.get("FACTORY26_MAX_OUTPUT_TOKENS", "8192")),
        }
        self.trace.record("model_request", endpoint=self.endpoint, model=self.model, payload=payload)
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last_error = "model request failed"
        for attempt in range(1, 4):
            request = urllib.request.Request(
                self.endpoint,
                data=encoded,
                method="POST",
                headers={
                    "authorization": "Bearer " + self.api_key,
                    "content-type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=240) as response:
                    body = json.loads(response.read().decode("utf-8"))
                message = dict(body["choices"][0]["message"])
                usage = body.get("usage") or {}
                prompt_tokens = int(usage.get("prompt_tokens") or 0)
                completion_tokens = int(usage.get("completion_tokens") or 0)
                self.total_prompt_tokens += prompt_tokens
                self.total_completion_tokens += completion_tokens
                reply = ModelReply(
                    content=str(message.get("content") or ""),
                    tool_calls=tuple(message.get("tool_calls") or ()),
                    raw_message=message,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
                self.trace.record(
                    "model_response",
                    model=self.model,
                    message=message,
                    usage={"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
                )
                return reply
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, ValueError) as exc:
                detail = ""
                if isinstance(exc, urllib.error.HTTPError):
                    try:
                        detail = exc.read().decode("utf-8", errors="replace")[-1000:]
                    except OSError:
                        detail = ""
                last_error = f"attempt {attempt}: {exc} {detail}".strip()
                self.trace.record("model_error", attempt=attempt, error=last_error)
                if attempt < 3:
                    time.sleep(attempt)
        raise RuntimeError(last_error)
