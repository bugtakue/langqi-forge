from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from factory26_harness import cli
from factory26_harness.submission_bundle import (
    SOURCE_MANIFEST_NAME,
    build_submission_bundle,
    require_external_output_directory,
    verify_source_manifest,
)


class SubmissionBundleTests(unittest.TestCase):
    def _source_tree(self, root: Path) -> Path:
        source = root / "source"
        (source / "arcbench_agent_runtime").mkdir(parents=True)
        (source / "factory26_harness" / "templates" / "github").mkdir(
            parents=True
        )
        (source / "factory26_harness" / "templates" / "sheet").mkdir(
            parents=True
        )
        (source / "main.py").write_text("print('entry')\n", encoding="utf-8")
        (source / "requirements.txt").write_text(
            "pyyaml>=6,<7\n", encoding="utf-8"
        )
        (source / "arcbench_agent_runtime" / "__init__.py").write_text(
            "", encoding="utf-8"
        )
        (source / "factory26_harness" / "__init__.py").write_text(
            "", encoding="utf-8"
        )
        (source / "factory26_harness" / "cli.py").write_text(
            "VALUE = 1\n", encoding="utf-8"
        )
        (source / "factory26_harness" / "evidence.py").write_text(
            "EXCLUDED = True\n", encoding="utf-8"
        )
        (
            source
            / "factory26_harness"
            / "templates"
            / "github"
            / "app.js"
        ).write_text("export {}\n", encoding="utf-8")
        (
            source
            / "factory26_harness"
            / "templates"
            / "sheet"
            / "app.js"
        ).write_text("export {}\n", encoding="utf-8")
        (source / "tests").mkdir()
        (source / "tests" / "secret-token.txt").write_text(
            "must-not-ship\n", encoding="utf-8"
        )
        subprocess.run(["git", "init", "-q"], cwd=source, check=True)
        subprocess.run(
            ["git", "config", "user.email", "bundle@example.invalid"],
            cwd=source,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Bundle Test"],
            cwd=source,
            check=True,
        )
        subprocess.run(["git", "add", "."], cwd=source, check=True)
        subprocess.run(
            ["git", "commit", "-qm", "fixture"], cwd=source, check=True
        )
        return source

    def test_bundle_is_minimal_deterministic_and_manifest_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source_tree(root)
            first = root / "one.zip"
            second = root / "two.zip"
            first_result = build_submission_bundle(source, first)
            second_result = build_submission_bundle(source, second)
            self.assertEqual(first_result["sha256"], second_result["sha256"])
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                names = set(archive.namelist())
                self.assertIn("main.py", names)
                self.assertIn(SOURCE_MANIFEST_NAME, names)
                self.assertNotIn("tests/secret-token.txt", names)
                self.assertNotIn("factory26_harness/evidence.py", names)
                manifest = json.loads(archive.read(SOURCE_MANIFEST_NAME))
                self.assertEqual(
                    manifest["source_revision"], first_result["source_revision"]
                )
                self.assertEqual(
                    set(manifest["files"]), names - {SOURCE_MANIFEST_NAME}
                )

            extracted = root / "extracted"
            with zipfile.ZipFile(first) as archive:
                archive.extractall(extracted)
            verified = verify_source_manifest(extracted)
            self.assertEqual(
                verified["source_revision"], first_result["source_revision"]
            )

    def test_unpacked_bundle_rejects_internal_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source_tree(root)
            bundle = root / "agent.zip"
            build_submission_bundle(source, bundle)
            extracted = root / "extracted"
            with zipfile.ZipFile(bundle) as archive:
                archive.extractall(extracted)

            require_external_output_directory(extracted, root / "workspace")
            with self.assertRaisesRegex(RuntimeError, "requires --output-dir outside"):
                require_external_output_directory(
                    extracted, extracted / "generated-project"
                )

    def test_source_identity_prefers_bundle_manifest_inside_outer_git(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source_tree(root)
            bundle = root / "agent.zip"
            result = build_submission_bundle(source, bundle)
            extracted = source / "outer-container" / "unpacked"
            with zipfile.ZipFile(bundle) as archive:
                archive.extractall(extracted)

            with patch.object(cli, "SOURCE_ROOT", extracted):
                identity = cli._source_identity()
                with patch.dict(
                    cli.os.environ,
                    {"FACTORY26_SOURCE_REVISION": "0" * 40},
                ):
                    with self.assertRaisesRegex(
                        RuntimeError, "does not match verified"
                    ):
                        cli._source_identity()

            self.assertEqual(identity["revision"], result["source_revision"])
            self.assertEqual(identity["source"], "verified-submission-manifest")
            self.assertTrue(identity["worktree_clean"])

    def test_manifest_verification_rejects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source_tree(root)
            bundle = root / "agent.zip"
            build_submission_bundle(source, bundle)
            extracted = root / "extracted"
            with zipfile.ZipFile(bundle) as archive:
                archive.extractall(extracted)
            (extracted / "main.py").write_text(
                "print('tampered')\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                RuntimeError, "does not match manifest"
            ):
                verify_source_manifest(extracted)

    def test_manifest_verification_rejects_unlisted_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source_tree(root)
            bundle = root / "agent.zip"
            build_submission_bundle(source, bundle)
            extracted = root / "extracted"
            with zipfile.ZipFile(bundle) as archive:
                archive.extractall(extracted)
            (extracted / "sitecustomize.py").write_text(
                "raise RuntimeError('unexpected')\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(RuntimeError, "file set does not match"):
                verify_source_manifest(extracted)

    def test_clean_source_is_required_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source_tree(root)
            (source / "main.py").write_text(
                "print('dirty')\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(RuntimeError, "dirty source tree"):
                build_submission_bundle(source, root / "agent.zip")


if __name__ == "__main__":
    unittest.main()
