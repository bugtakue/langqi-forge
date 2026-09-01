from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .trace import ProductionTrace


class ModelBudgetExceeded(RuntimeError):
    """A deterministic local model budget was exceeded."""


@dataclass(frozen=True)
class ModelReply:
    content: str
    tool_calls: tuple[dict[str, Any], ...]
    raw_message: dict[str, Any]
    prompt_tokens: int
    completion_tokens: int
    response_id: str


class OpenAIChatClient:
    def __init__(self, trace: ProductionTrace) -> None:
        self.api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.base_url = os.environ.get("OPENAI_BASE_URL", "").strip()
        self.model = os.environ.get("MODEL", "").strip()
        self.trace = trace
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.request_count = 0
        self.http_attempt_count = 0
        self.max_requests = max(
            1, int(os.environ.get("FACTORY26_MAX_MODEL_REQUESTS", "64"))
        )
        self.max_response_bytes = max(
            1024, int(os.environ.get("FACTORY26_MAX_MODEL_RESPONSE_BYTES", "10000000"))
        )
        self.max_request_bytes = max(
            1024, int(os.environ.get("FACTORY26_MAX_MODEL_REQUEST_BYTES", "5000000"))
        )
        self.max_total_prompt_tokens = max(
            1, int(os.environ.get("FACTORY26_MAX_TOTAL_PROMPT_TOKENS", "100000"))
        )
        self.max_total_completion_tokens = max(
            1,
            int(os.environ.get("FACTORY26_MAX_TOTAL_COMPLETION_TOKENS", "100000")),
        )
        if not self.api_key or not self.base_url or not self.model:
            raise RuntimeError("OPENAI_API_KEY, OPENAI_BASE_URL and MODEL are required")

    @property
    def endpoint(self) -> str:
        normalized = self.base_url.rstrip("/")
        return (
            normalized
            if normalized.endswith("/chat/completions")
            else normalized + "/chat/completions"
        )

    @property
    def endpoint_host(self) -> str:
        return str(urlsplit(self.endpoint).hostname or "")

    @property
    def gateway_provenance(self) -> str:
        host = self.endpoint_host.lower()
        if host == "dashscope.aliyuncs.com" or host.endswith(".maas.aliyuncs.com"):
            return "alibaba-cloud-bailian"
        if host in {"127.0.0.1", "localhost", "::1"}:
            return "local-openai-protocol-fixture"
        return "openai-compatible-runtime"

    def gateway_evidence(self) -> dict[str, Any]:
        return {
            "provenance": self.gateway_provenance,
            "endpoint_host": self.endpoint_host,
            "model": self.model,
        }

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        max_tokens: int | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        max_attempts: int = 3,
        timeout_seconds: int | None = None,
    ) -> ModelReply:
        if not 1 <= max_attempts <= 3:
            raise ValueError("max_attempts must be between 1 and 3")
        request_timeout = (
            int(timeout_seconds)
            if timeout_seconds is not None
            else int(os.environ.get("FACTORY26_MODEL_TIMEOUT_SECONDS", "240"))
        )
        if not 1 <= request_timeout <= 240:
            raise ValueError("model timeout must be between 1 and 240 seconds")
        if self.request_count >= self.max_requests:
            self.trace.record(
                "model_budget_exhausted",
                request_count=self.request_count,
                maximum_requests=self.max_requests,
            )
            raise RuntimeError(
                f"model request budget exhausted at {self.max_requests} calls"
            )
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens
            if max_tokens is not None
            else int(os.environ.get("FACTORY26_MAX_OUTPUT_TOKENS", "8192")),
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice if tool_choice is not None else "auto"
        elif tool_choice is not None:
            raise ValueError("tool_choice requires at least one tool schema")
        self.trace.record(
            "model_request",
            endpoint=self.endpoint,
            model=self.model,
            gateway=self.gateway_evidence(),
            payload=payload,
            request_policy={
                "max_attempts": max_attempts,
                "timeout_seconds": request_timeout,
            },
        )
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(encoded) > self.max_request_bytes:
            raise RuntimeError(
                f"model request exceeds {self.max_request_bytes} byte safety limit"
            )
        last_error = "model request failed"
        for attempt in range(1, max_attempts + 1):
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
                self.http_attempt_count += 1
                with urllib.request.urlopen(
                    request, timeout=request_timeout
                ) as response:
                    declared_length = int(response.headers.get("content-length") or 0)
                    if declared_length > self.max_response_bytes:
                        raise ValueError(
                            "model response exceeds declared byte safety limit"
                        )
                    raw_body = response.read(self.max_response_bytes + 1)
                    if len(raw_body) > self.max_response_bytes:
                        raise ValueError("model response exceeds byte safety limit")
                    body = json.loads(raw_body.decode("utf-8"))
                choices = body.get("choices") if isinstance(body, dict) else None
                if not isinstance(choices, list) or not choices:
                    raise ValueError("model response choices are missing")
                raw_message = (
                    choices[0].get("message") if isinstance(choices[0], dict) else None
                )
                if not isinstance(raw_message, dict):
                    raise ValueError("model response message is invalid")
                message = dict(raw_message)
                if not isinstance(message.get("tool_calls") or [], list):
                    raise ValueError("model response tool_calls must be an array")
                usage = body.get("usage") or {}
                prompt_tokens = int(
                    usage.get("prompt_tokens") or usage.get("input_tokens") or 0
                )
                completion_tokens = int(
                    usage.get("completion_tokens") or usage.get("output_tokens") or 0
                )
                if prompt_tokens < 0 or completion_tokens < 0:
                    raise ValueError("model token usage cannot be negative")
                if (
                    self.total_prompt_tokens + prompt_tokens
                    > self.max_total_prompt_tokens
                    or self.total_completion_tokens + completion_tokens
                    > self.max_total_completion_tokens
                ):
                    self.trace.record(
                        "model_budget_exhausted",
                        prompt_tokens_observed=prompt_tokens,
                        completion_tokens_observed=completion_tokens,
                        total_prompt_tokens=self.total_prompt_tokens,
                        total_completion_tokens=self.total_completion_tokens,
                        maximum_prompt_tokens=self.max_total_prompt_tokens,
                        maximum_completion_tokens=self.max_total_completion_tokens,
                    )
                    raise ModelBudgetExceeded("model token budget exceeded")
                response_id = str(body.get("id") or "")
                self.total_prompt_tokens += prompt_tokens
                self.total_completion_tokens += completion_tokens
                self.request_count += 1
                reply = ModelReply(
                    content=str(message.get("content") or ""),
                    tool_calls=tuple(message.get("tool_calls") or ()),
                    raw_message=message,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    response_id=response_id,
                )
                self.trace.record(
                    "model_response",
                    model=self.model,
                    gateway=self.gateway_evidence(),
                    response_id=response_id,
                    message=message,
                    usage={
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                    },
                )
                return reply
            except (
                urllib.error.URLError,
                urllib.error.HTTPError,
                TimeoutError,
                ConnectionError,
                KeyError,
                ValueError,
            ) as exc:
                detail = ""
                if isinstance(exc, urllib.error.HTTPError):
                    try:
                        detail = exc.read().decode("utf-8", errors="replace")[-1000:]
                    except OSError:
                        detail = ""
                last_error = f"attempt {attempt}: {exc} {detail}".strip()
                self.trace.record("model_error", attempt=attempt, error=last_error)
                if attempt < max_attempts:
                    time.sleep(attempt)
        raise RuntimeError(last_error)
