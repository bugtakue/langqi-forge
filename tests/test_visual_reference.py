from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
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
