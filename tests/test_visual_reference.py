from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from factory26_harness.trace import ProductionTrace, verify_trace_rows
from factory26_harness.visual_reference import (
    VisualReferenceClient,
    referenced_images,
    resolve_visual_gateway,
)
from factory26_harness.workspace_tools import WorkspaceTools


TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9XPdUAAAAASUVORK5CYII="
)


class FakeResponse:
    headers: dict[str, str] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    @staticmethod
    def read(_limit: int) -> bytes:
        return json.dumps({
            "choices": [{"message": {"content": "Two-column layout with a blue Save button."}}],
            "usage": {"prompt_tokens": 42, "completion_tokens": 12},
        }).encode("utf-8")


class VisualReferenceTests(unittest.TestCase):
    def test_exhausted_budget_exposes_only_still_usable_cached_images(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            references = root / "task/reference"
            references.mkdir(parents=True)
            (references / "home.png").write_bytes(TINY_PNG)
            (references / "other.png").write_bytes(TINY_PNG + b"\n")
            trace = ProductionTrace(root / "trace.jsonl")
            configuration, _ = resolve_visual_gateway({
                "VISUAL_API_KEY": "fixture-secret",
                "VISUAL_BASE_URL": "https://vision.example.test/v1",
                "VISUAL_MODEL": "fixture-vision",
            })
            client = VisualReferenceClient(root / "task", trace, configuration)
            client.max_calls = 1
            self.assertTrue(client.can_inspect("reference/home.png"))
            self.assertTrue(client.can_inspect("reference/other.png"))
            with patch("factory26_harness.visual_reference.urllib.request.urlopen",
                       return_value=FakeResponse()) as opener:
                client.describe("reference/home.png")
                self.assertEqual(client.calls, 1)
                self.assertTrue(client.can_inspect("reference/home.png"))
                self.assertFalse(client.can_inspect("reference/other.png"))
                available = tuple(path for path in ("reference/home.png", "reference/other.png")
                                  if client.can_inspect(path))
                tools = WorkspaceTools(root / "output", trace, 3910,
                                       visual_client=client, reference_paths=available)
                visual = next(item["function"] for item in tools.schemas()
                              if item["function"]["name"] == "inspect_reference")
                self.assertEqual(visual["parameters"]["properties"]["path"]["enum"],
                                 ["reference/home.png"])
                self.assertTrue(client.describe("reference/home.png")["cached"])
                opener.assert_called_once()
            # Cached captions are content-bound, not permission to reuse an
            # old caption after the image at the same path has changed.
            (references / "home.png").write_bytes(TINY_PNG + b"\n")
            self.assertFalse(client.can_inspect("reference/home.png"))

    def test_exhausted_failed_visual_request_is_not_available_to_next_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "task/reference").mkdir(parents=True)
            (root / "task/reference/home.png").write_bytes(TINY_PNG)
            trace = ProductionTrace(root / "trace.jsonl")
            configuration, _ = resolve_visual_gateway({
                "VISUAL_API_KEY": "fixture-secret",
                "VISUAL_BASE_URL": "https://vision.example.test/v1",
                "VISUAL_MODEL": "fixture-vision",
            })
            client = VisualReferenceClient(root / "task", trace, configuration)
            client.max_calls = 1
            with patch("factory26_harness.visual_reference.urllib.request.urlopen",
                       side_effect=TimeoutError("fixture")) as opener:
                with self.assertRaises(RuntimeError):
                    client.describe("reference/home.png")
                self.assertFalse(client.can_inspect("reference/home.png"))
                available = tuple(path for path in ("reference/home.png",)
                                  if client.can_inspect(path))
                tools = WorkspaceTools(root / "output", trace, 3910,
                                       visual_client=client, reference_paths=available)
                self.assertNotIn("inspect_reference", [item["function"]["name"]
                                                       for item in tools.schemas()])
                opener.assert_called_once()

    def _response_case(self, response_body: bytes, network_error: Exception | None = None):
        """Only local response fixtures; never call a model or expose image bytes."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "task/reference").mkdir(parents=True)
            (root / "task/reference/home.png").write_bytes(TINY_PNG)
            trace = ProductionTrace(root / "trace.jsonl", stdout_progress=True)
            configuration, _ = resolve_visual_gateway({
                "VISUAL_API_KEY": "fixture-secret",
                "VISUAL_BASE_URL": "https://vision.example.test/v1",
                "VISUAL_MODEL": "fixture-vision",
            })
            client = VisualReferenceClient(root / "task", trace, configuration)
            response = FakeResponse()
            response.read = lambda _limit: response_body
            output = io.StringIO()
            error = None
            with contextlib.redirect_stdout(output), patch(
                "factory26_harness.visual_reference.urllib.request.urlopen",
                return_value=response, side_effect=network_error,
            ) as opener:
                try:
                    answer = client.describe("reference/home.png")
                except RuntimeError as exc:
                    error, answer = str(exc), None
            rows = [json.loads(line) for line in trace.path.read_text().splitlines()]
            self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])
            self.assertEqual(opener.call_count, 1)
            return client, answer, error, rows[-1], output.getvalue()

    def test_empty_caption_keeps_reported_usage_and_safe_failure_reason(self) -> None:
        client, answer, error, row, output = self._response_case(json.dumps({
            "choices": [{"finish_reason": "length", "message": {
                "content": None, "reasoning_content": "private-provider-body",
            }}],
            "usage": {"prompt_tokens": 42, "completion_tokens": 500},
        }).encode())
        self.assertIsNone(answer)
        self.assertIn("empty_caption", error)
        self.assertEqual((client.prompt_tokens, client.completion_tokens), (42, 500))
        self.assertEqual(row["payload"]["finish_reason"], "length")
        self.assertEqual(row["payload"]["usage_status"], "reported")
        self.assertIn('"error_category": "empty_caption"', output)
        self.assertNotIn("private-provider-body", str(row) + output + error)

    def test_malformed_visual_responses_have_bounded_categories(self) -> None:
        for body, category in (
            (b'{"error": "private-provider-body"', "invalid_json"),
            (b'[]', "invalid_response"),
            (b'{"choices": []}', "invalid_response"),
            (b'{"choices": [{"message": {"content": 42}}]}', "invalid_caption"),
            (b'x' * 100_001, "response_too_large"),
        ):
            with self.subTest(category=category):
                client, answer, error, row, output = self._response_case(body)
                self.assertIsNone(answer)
                self.assertIn(category, error)
                self.assertEqual(row["payload"]["error_category"], category)
                self.assertEqual(client.calls, 1)
                self.assertNotIn("private-provider-body", str(row) + output + error)

    def test_visual_usage_is_sanitized_and_not_inferred_when_missing(self) -> None:
        for usage, status, totals in (
            ({"prompt_tokens": 8, "completion_tokens": 9, "extra": "private-provider-body"},
             "reported", (8, 9)),
            ({"prompt_tokens": 8}, "partial", (8, 0)),
            ({"prompt_tokens": True, "completion_tokens": -1}, "invalid", (0, 0)),
            (None, "unavailable", (0, 0)),
        ):
            with self.subTest(status=status):
                client, answer, error, row, output = self._response_case(json.dumps({
                    "choices": [{"finish_reason": "private-provider-body", "message": {
                        "content": [{"type": "text", "text": "A visible Save button."}],
                    }}], "usage": usage,
                }).encode())
                self.assertIsNone(error)
                self.assertEqual(answer["description"], "A visible Save button.")
                self.assertEqual((client.prompt_tokens, client.completion_tokens), totals)
                self.assertEqual(row["payload"]["usage_status"], status)
                self.assertEqual(row["payload"]["finish_reason"], "unknown")
                self.assertNotIn("private-provider-body", str(row) + output)
                self.assertNotIn("A visible Save button.", output)

    def test_network_failure_does_not_leak_provider_detail_or_guess_usage(self) -> None:
        for failure, category in (
            (urllib.error.HTTPError("https://vision.example.test", 429,
                                    "private-provider-body", {}, None), "http_error"),
            (urllib.error.URLError("private-provider-body"), "transport_error"),
            (TimeoutError("private-provider-body"), "transport_error"),
        ):
            with self.subTest(category=category, error_type=type(failure).__name__):
                client, answer, error, row, output = self._response_case(b"", failure)
                self.assertIsNone(answer)
                self.assertIn(category, error)
                self.assertEqual(row["payload"]["usage_status"], "unavailable")
                self.assertEqual(row["payload"]["usage"], {})
                self.assertEqual((client.prompt_tokens, client.completion_tokens), (0, 0))
                self.assertNotIn("private-provider-body", str(row) + output + error)
                if category == "http_error":
                    self.assertEqual(row["payload"]["http_status"], 429)

    def test_named_visual_model_can_reuse_the_coding_gateway(self) -> None:
        environment = {
            "OPENAI_API_KEY": "shared-fixture-secret",
            "OPENAI_BASE_URL": "https://gateway.example.test/v1",
            "VISUAL_MODEL": "fixture-vision",
        }
        configuration, status = resolve_visual_gateway(environment)
        self.assertEqual(status, "available")
        self.assertIsNotNone(configuration)
        self.assertEqual(configuration.source, "shared-model-gateway")
        self.assertEqual(configuration.model, "fixture-vision")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "task/reference").mkdir(parents=True)
            (root / "task/reference/home.png").write_bytes(TINY_PNG)
            trace = ProductionTrace(root / "trace.jsonl")
            with patch(
                "factory26_harness.visual_reference.urllib.request.urlopen",
                return_value=FakeResponse(),
            ) as opener:
                client = VisualReferenceClient(root / "task", trace, configuration)
                self.assertEqual(client.describe("reference/home.png")["description"],
                                 "Two-column layout with a blue Save button.")
            self.assertEqual(opener.call_args.args[0].get_header("Authorization"),
                             "Bearer shared-fixture-secret")
            self.assertNotIn("shared-fixture-secret", trace.path.read_text(encoding="utf-8"))

    def test_partial_explicit_visual_configuration_never_falls_back(self) -> None:
        shared = {
            "OPENAI_API_KEY": "shared-fixture-secret",
            "OPENAI_BASE_URL": "https://gateway.example.test/v1",
            "VISUAL_MODEL": "fixture-vision",
        }
        for extra in ({"VISUAL_API_KEY": "explicit-secret"},
                      {"VISUAL_BASE_URL": "https://vision.example.test/v1"}):
            with self.subTest(extra=extra):
                configuration, status = resolve_visual_gateway({**shared, **extra})
                self.assertIsNone(configuration)
                self.assertIn("incomplete", status)
        explicit, status = resolve_visual_gateway({
            **shared,
            "VISUAL_API_KEY": "explicit-secret",
            "VISUAL_BASE_URL": "https://vision.example.test/v1",
        })
        self.assertEqual(status, "available")
        self.assertEqual(explicit.source, "explicit-vision-gateway")
        self.assertEqual(explicit.api_key, "explicit-secret")
        self.assertEqual(resolve_visual_gateway({**shared, "VISUAL_MODEL": ""}),
                         (None, "disabled"))

    def test_symlinked_reference_directory_cannot_leave_the_task(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "task").mkdir()
            (root / "outside").mkdir()
            (root / "task/reference").symlink_to(root / "outside", target_is_directory=True)
            trace = ProductionTrace(root / "trace.jsonl")
            configuration, _ = resolve_visual_gateway({
                "VISUAL_API_KEY": "fixture-secret",
                "VISUAL_BASE_URL": "https://vision.example.test/v1",
                "VISUAL_MODEL": "fixture-vision",
            })
            with self.assertRaisesRegex(ValueError, "cannot be a symlink"):
                VisualReferenceClient(root / "task", trace, configuration)

    def test_only_explicit_reference_paths_are_extracted(self) -> None:
        self.assertEqual(
            referenced_images([
                "Home ![image](./reference/home.png), detail reference/detail.webp",
                "Again ./reference/home.png; unrelated assets/logo.png",
            ]),
            ("reference/detail.webp", "reference/home.png"),
        )

    def test_optional_tool_inspects_once_without_logging_image_or_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            references = root / "task/reference"
            references.mkdir(parents=True)
            (references / "home.png").write_bytes(TINY_PNG)
            trace = ProductionTrace(root / "output/.arc/trace.jsonl")
            environment = {
                "VISUAL_API_KEY": "vision-test-secret",
                "VISUAL_BASE_URL": "https://vision.example.test/v1",
                "VISUAL_MODEL": "fixture-vision",
            }
            with (
                patch.dict(os.environ, environment),
                patch("factory26_harness.visual_reference.urllib.request.urlopen", return_value=FakeResponse()) as opener,
            ):
                client = VisualReferenceClient(root / "task", trace)
                tools = WorkspaceTools(
                    root / "output", trace, 3910,
                    visual_client=client,
                    reference_paths=("reference/home.png",),
                )
                self.assertIn("inspect_reference", [entry["function"]["name"] for entry in tools.schemas()])
                first = json.loads(tools.execute("inspect_reference", {"path": "reference/home.png"}))
                second = json.loads(tools.execute("inspect_reference", {"path": "reference/home.png"}))
                rejected = json.loads(tools.execute("inspect_reference", {"path": "reference/other.png"}))
                self.assertEqual(opener.call_count, 1)
                sent = json.loads(opener.call_args.args[0].data)
                self.assertTrue(sent["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
                self.assertEqual(first["description"], "Two-column layout with a blue Save button.")
                self.assertTrue(second["cached"])
                self.assertFalse(rejected["ok"])
                self.assertEqual(client.calls, 1)
                self.assertEqual(client.prompt_tokens, 42)
            encoded_trace = trace.path.read_text(encoding="utf-8")
            self.assertNotIn("vision-test-secret", encoded_trace)
            self.assertNotIn(base64.b64encode(TINY_PNG).decode("ascii"), encoded_trace)
            rows = [json.loads(line) for line in encoded_trace.splitlines()]
            self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])

    def test_reference_path_escape_is_rejected_before_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "task/reference").mkdir(parents=True)
            trace = ProductionTrace(root / "trace.jsonl")
            with patch.dict(os.environ, {
                "VISUAL_API_KEY": "vision-test-secret",
                "VISUAL_BASE_URL": "https://vision.example.test/v1",
                "VISUAL_MODEL": "fixture-vision",
            }):
                client = VisualReferenceClient(root / "task", trace)
                for unsafe in ("../private.png", "reference/../private.png", "/tmp/private.png"):
                    with self.assertRaises(ValueError):
                        client.describe(unsafe)
                self.assertEqual(client.calls, 0)


if __name__ == "__main__":
    unittest.main()
