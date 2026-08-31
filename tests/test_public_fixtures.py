from __future__ import annotations

import unittest

from factory26_harness.public_fixtures import public_fixture_environment


class PublicFixtureTests(unittest.TestCase):
    def test_github_environment_has_isolated_accounts_and_urls(self) -> None:
        environment = public_fixture_environment("github", "http://127.0.0.1:3401")
        self.assertEqual(environment["E2E_PUBLIC_REPOSITORY_NAME"], "roadmap-app")
        self.assertTrue(environment["E2E_PUBLIC_REPOSITORY_URL"].startswith("http://127.0.0.1:3401/"))
        self.assertNotEqual(
            environment["E2E_LOGIN_USERNAME"],
            environment["E2E_PASSWORD_CHANGE_USERNAME"],
        )
        self.assertEqual(public_fixture_environment("sheet", "http://localhost:1"), {})

    def test_adversarial_profile_renames_accounts_and_domain_objects(self) -> None:
        baseline = public_fixture_environment("github", "http://127.0.0.1:3401")
        mutated = public_fixture_environment(
            "github", "http://127.0.0.1:3401", "adversarial"
        )
        self.assertNotEqual(mutated["E2E_LOGIN_USERNAME"], baseline["E2E_LOGIN_USERNAME"])
        self.assertEqual(mutated["E2E_PUBLIC_REPOSITORY_NAME"], "atlas-service")
        self.assertEqual(
            mutated["E2E_PUBLIC_REPOSITORY_URL"],
            "http://127.0.0.1:3401/open-labs/atlas-service",
        )
        self.assertEqual(mutated["E2E_ISSUE_LABEL"], "severity:critical")

    def test_rejects_unknown_fixture_profile(self) -> None:
        with self.assertRaises(ValueError):
            public_fixture_environment("github", "http://localhost:1", "unknown")
