"""Optional, task-neutral visual inspection of organizer-provided reference images.

Image bytes go only to the configured vision gateway. They are never written to
the production trace or copied into the generated application.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlsplit

from .trace import ProductionTrace


REFERENCE_PATTERN = re.compile(r"(?:\./)?(reference/[A-Za-z0-9_./-]+\.(?:png|jpg|jpeg|webp))\b", re.IGNORECASE)
IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
MAX_IMAGE_BYTES = 5_000_000
MAX_VISUAL_RESPONSE_BYTES = 100_000
MAX_CAPTION_CHARS = 1_500


class _VisualResponseError(ValueError):
    """A fixed diagnostic code, never provider-controlled response text."""


def _reported_usage(value: Any) -> tuple[dict[str, int], str]:
    if value is None:
        return {}, "unavailable"
    if not isinstance(value, dict):
        return {}, "invalid"
    usage = {}
    invalid = False
    for key in ("prompt_tokens", "completion_tokens"):
        if key not in value:
            continue
        count = value[key]
        if type(count) is int and count >= 0:
            usage[key] = count
        else:
            invalid = True
    status = "invalid" if invalid else (
        "reported" if len(usage) == 2 else "partial" if usage else "unavailable"
    )
    return usage, status


def _visual_message(result: dict[str, Any]) -> tuple[dict[str, Any], str]:
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise _VisualResponseError("invalid_response")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise _VisualResponseError("invalid_response")
    reason = choices[0].get("finish_reason")
    allowed = {"stop", "length", "tool_calls", "function_call", "content_filter"}
    return message, reason if isinstance(reason, str) and reason in allowed else "unknown"


def _visual_caption(message: dict[str, Any]) -> str:
    caption = message.get("content")
    if caption is None:
        caption = ""
    if isinstance(caption, list):
        caption = " ".join(
            item["text"] for item in caption
            if isinstance(item, dict) and item.get("type") == "text"
            and isinstance(item.get("text"), str)
        )
    if not isinstance(caption, str):
        raise _VisualResponseError("invalid_caption")
    caption = caption.strip()[:MAX_CAPTION_CHARS]
    if not caption:
        raise _VisualResponseError("empty_caption")
    return caption


@dataclass(frozen=True)
class VisualGatewayConfiguration:
    api_key: str
    base_url: str
    model: str
    source: str


def resolve_visual_gateway(
    environment: Mapping[str, str] | None = None,
) -> tuple[VisualGatewayConfiguration | None, str]:
    """Use an explicit vision gateway, or a named vision model on the coding gateway."""

    values = os.environ if environment is None else environment
    visual_key = values.get("VISUAL_API_KEY", "").strip()
    visual_base = values.get("VISUAL_BASE_URL", "").strip()
    visual_model = values.get("VISUAL_MODEL", "").strip()
    if not any((visual_key, visual_base, visual_model)):
        return None, "disabled"
    if not visual_model or bool(visual_key) != bool(visual_base):
        return None, "incomplete VISUAL_MODEL or explicit VISUAL_API_KEY/VISUAL_BASE_URL configuration"
    if visual_key and visual_base:
        return (
            VisualGatewayConfiguration(visual_key, visual_base, visual_model, "explicit-vision-gateway"),
            "available",
        )
    shared_key = values.get("OPENAI_API_KEY", "").strip()
    shared_base = values.get("OPENAI_BASE_URL", "").strip()
    if not shared_key or not shared_base:
        return None, "VISUAL_MODEL requires a complete shared OPENAI_API_KEY/OPENAI_BASE_URL gateway"
    return (
        VisualGatewayConfiguration(shared_key, shared_base, visual_model, "shared-model-gateway"),
        "available",
    )


def referenced_images(descriptions: list[str]) -> tuple[str, ...]:
    """List only image names explicitly referenced by current requirements."""
    return tuple(sorted({match.group(1) for description in descriptions for match in REFERENCE_PATTERN.finditer(description)}))


class VisualReferenceClient:
    def __init__(
        self,
        requirement_dir: Path,
        trace: ProductionTrace,
        configuration: VisualGatewayConfiguration | None = None,
    ) -> None:
        self.requirement_dir = (requirement_dir.parent if requirement_dir.is_file() else requirement_dir).resolve()
        reference_path = self.requirement_dir / "reference"
        if reference_path.is_symlink():
            raise ValueError("reference directory cannot be a symlink")
        self.reference_root = reference_path.resolve()
        self.trace = trace
        if configuration is None:
            configuration, status = resolve_visual_gateway()
            if configuration is None:
                raise ValueError(status)
        self.api_key = configuration.api_key
        self.base_url = configuration.base_url
        self.model = configuration.model
        self.gateway_source = configuration.source
        self.endpoint = self.base_url.rstrip("/")
        if not self.endpoint.endswith("/chat/completions"):
            self.endpoint += "/chat/completions"
        destination = urlsplit(self.endpoint)
        if (
            not destination.hostname
            or destination.username
            or destination.password
            or destination.query
            or destination.fragment
            or not (
                destination.scheme == "https"
                or (destination.scheme == "http" and destination.hostname in {"127.0.0.1", "localhost"})
            )
        ):
            raise ValueError("visual gateway requires HTTPS or a local test endpoint")
        self.max_calls = max(1, min(24, int(os.environ.get("FACTORY26_MAX_VISUAL_CALLS", "8"))))
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self._cache: dict[str, dict[str, Any]] = {}

    def _image(self, relative: str) -> tuple[bytes, str, str]:
        if "\\" in relative:
            raise ValueError("reference path must be POSIX-style")
        name = PurePosixPath(relative)
        if name.is_absolute() or ".." in name.parts or len(name.parts) < 2 or name.parts[0] != "reference":
            raise ValueError("only reference/ images can be inspected")
        mime = IMAGE_MIME.get(name.suffix.lower())
        if not mime:
            raise ValueError("unsupported reference image type")
        candidate = self.requirement_dir / name.as_posix()
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError("reference image is missing or a symlink")
        resolved = candidate.resolve()
        if self.reference_root not in resolved.parents:
            raise ValueError("reference image escapes its directory")
        if resolved.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError("reference image exceeds byte limit")
        raw = resolved.read_bytes()
        if not (
            (mime == "image/png" and raw.startswith(b"\x89PNG\r\n\x1a\n"))
            or (mime == "image/jpeg" and raw.startswith(b"\xff\xd8\xff"))
            or (mime == "image/webp" and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP")
        ):
            raise ValueError("reference image signature does not match its type")
        return raw, mime, hashlib.sha256(raw).hexdigest()

    def can_inspect(self, relative: str) -> bool:
        try:
            self._image(relative)
            return True
        except (OSError, ValueError):
            return False

    def describe(self, relative: str) -> dict[str, Any]:
        raw, mime, digest = self._image(relative)
        if digest in self._cache:
            return {**self._cache[digest], "cached": True}
        if self.calls >= self.max_calls:
            raise RuntimeError("visual reference call budget exhausted")
        payload = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": (
                        "Describe this UI reference for a coding agent in at most 180 words. "
                        "State visible layout, spacing, hierarchy, colors, labels, controls and "
                        "distinctive interaction affordances. Do not invent hidden behavior or data."
                    )},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}",
                        "detail": "high",
                    }},
                ],
            }],
            "max_tokens": 500,
        }
        self.calls += 1
        self.trace.record(
            "visual_reference_request",
            path=relative,
            image_sha256=digest,
            image_bytes=len(raw),
            model=self.model,
            endpoint_host=urlsplit(self.endpoint).hostname,
        )
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"authorization": "Bearer " + self.api_key, "content-type": "application/json"},
        )
        diagnostic: dict[str, Any] = {"usage": {}, "usage_status": "unavailable",
                                      "finish_reason": "unknown"}
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                body = response.read(MAX_VISUAL_RESPONSE_BYTES + 1)
            diagnostic["response_bytes"] = len(body)
            if len(body) > MAX_VISUAL_RESPONSE_BYTES:
                raise _VisualResponseError("response_too_large")
            result = json.loads(body.decode("utf-8"))
            if not isinstance(result, dict):
                raise _VisualResponseError("invalid_response")
            usage, usage_status = _reported_usage(result.get("usage"))
            diagnostic.update(usage=usage, usage_status=usage_status)
            # A billed response may have no usable caption. Keep its reported
            # usage, but never invent usage for transport failures or missing fields.
            self.prompt_tokens += usage.get("prompt_tokens", 0)
            self.completion_tokens += usage.get("completion_tokens", 0)
            message, diagnostic["finish_reason"] = _visual_message(result)
            caption = _visual_caption(message)
            answer = {"path": relative, "image_sha256": digest, "description": caption, "cached": False}
            self._cache[digest] = answer
            self.trace.record("visual_reference_response", **answer, **diagnostic)
            return answer
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            if isinstance(exc, _VisualResponseError):
                category = str(exc)
            elif isinstance(exc, urllib.error.HTTPError):
                category = "http_error"
                diagnostic["http_status"] = exc.code
            elif isinstance(exc, (urllib.error.URLError, TimeoutError)):
                category = "transport_error"
            else:
                category = "invalid_json"
            self.trace.record(
                "visual_reference_error", path=relative, image_sha256=digest,
                error_type=type(exc).__name__, error_category=category, **diagnostic,
            )
            raise RuntimeError(
                f"visual reference unavailable: {category} (finish_reason={diagnostic['finish_reason']})"
            ) from exc
