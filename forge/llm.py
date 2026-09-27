"""Minimal OpenAI-compatible streaming chat client (stdlib only)."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    calls: int = 0
    failures: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    seconds: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, usage: dict, seconds: float) -> None:
        with self.lock:
            self.calls += 1
            self.seconds += seconds
            self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
            self.completion_tokens += int(usage.get("completion_tokens") or 0)
            details = usage.get("prompt_tokens_details") or {}
            self.cached_tokens += int(details.get("cached_tokens") or usage.get("prompt_cache_hit_tokens") or 0)

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "calls": self.calls,
                "failures": self.failures,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "cached_tokens": self.cached_tokens,
                "seconds": round(self.seconds, 1),
            }


class LLM:
    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None,
                 log=None) -> None:
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.arc-bench.com/v1").rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or ""
        self.model = model or os.environ.get("MODEL") or "deepseek-v4-flash"
        self.usage = Usage()
        self.log = log or (lambda *a, **k: None)
        if not self.api_key:
            raise LLMError("OPENAI_API_KEY is not set")

    def chat(self, messages: list[dict], *, model: str | None = None, max_tokens: int = 16000,
             temperature: float = 0.2, timeout: float = 600.0, retries: int = 3, tag: str = "",
             think: bool | None = None) -> str:
        model = model or self.model
        last_err: Exception | None = None
        for attempt in range(retries):
            t0 = time.time()
            try:
                text, usage = self._stream(messages, model, max_tokens, temperature, timeout, think)
                dt = time.time() - t0
                self.usage.add(usage, dt)
                self.log(f"llm[{tag}] model={model} {dt:.0f}s in={usage.get('prompt_tokens')} out={usage.get('completion_tokens')}")
                return text
            except LLMError as exc:
                last_err = exc
                with self.usage.lock:
                    self.usage.failures += 1
                msg = str(exc)
                self.log(f"llm[{tag}] attempt {attempt + 1} failed: {msg[:300]}")
                if "temperature" in msg and "only 1" in msg and temperature != 1:
                    temperature = 1
                    continue
                if think is False and "HTTP 400" in msg and "thinking" in msg.lower():
                    think = None
                    continue
                if "finish=length" in msg and max_tokens < 64000:
                    max_tokens = min(64000, max_tokens * 2)
                    if messages[-1].get("role") == "user" and "Keep internal reasoning brief" not in messages[-1]["content"]:
                        messages = messages[:-1] + [{"role": "user", "content": messages[-1]["content"] +
                                                     "\n\n(Keep internal reasoning brief; put your effort into the final answer.)"}]
                    continue
                if "HTTP 401" in msg or "HTTP 403" in msg or ("HTTP 400" in msg and "thinking" not in msg.lower()):
                    break
                time.sleep(min(60, 5 * (attempt + 1) ** 2))
        raise LLMError(f"model call failed after retries: {last_err}")

    def _stream(self, messages, model, max_tokens, temperature, timeout, think=None):
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if think is False:
            body["thinking"] = {"type": "disabled"}
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.api_key,
                     "Accept": "text/event-stream"},
            method="POST",
        )
        parts: list[str] = []
        usage: dict = {}
        finish = None
        deadline = time.time() + timeout
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                for raw in resp:
                    if time.time() > deadline:
                        raise LLMError("stream exceeded overall timeout")
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("error"):
                        raise LLMError(f"stream error: {json.dumps(chunk['error'])[:300]}")
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            parts.append(delta["content"])
                        if choice.get("finish_reason"):
                            finish = choice["finish_reason"]
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:500].decode("utf-8", errors="replace")
            raise LLMError(f"HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            raise LLMError(f"transport: {exc}") from exc
        text = "".join(parts)
        text = re.sub(r"^\s*<think>.*?</think>\s*", "", text, flags=re.S)
        if text.lstrip().startswith("<think>"):
            text = ""
        if not text.strip():
            raise LLMError(f"empty response (finish={finish})")
        if finish == "length":
            usage = dict(usage)
            usage["truncated"] = True
        return text, usage
