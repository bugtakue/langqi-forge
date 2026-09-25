"""Same-origin hash navigation is valid; network controls are unchanged."""
import unittest
from urllib.parse import urlsplit
from unittest.mock import Mock

from factory26_harness.browser_probe import _page_observation, _perform, validate_steps


class LocalHashNavigationTests(unittest.TestCase):
    def test_observation_reports_the_real_hash_route_without_origin(self):
        page = Mock()
        page.url = "http://127.0.0.1:33141/?view=compact#/settings?tab=profile"
        page.locator.return_value.inner_text.return_value = "Local page"
        page.evaluate.return_value = []
        result = _page_observation(page, expected=["Local page"], absent=["Signed out"])
        self.assertEqual(result["path"], "/?view=compact#/settings?tab=profile")
        self.assertEqual(result["missing_text"], [])
        self.assertEqual(result["unexpected_text"], [])
        self.assertNotIn("127.0.0.1", result["path"])

    def test_local_queries_and_fragments_keep_the_fixed_origin(self):
        base = "http://127.0.0.1:33141"
        for path in ("/#/signin", "/#/settings?tab=profile", "/docs?section=a#details",
                     "/safe#fragment", "/#/route/https://example.test", "/#//example.test"):
            with self.subTest(path=path):
                plan = validate_steps([{"action": "navigate", "path": path,
                                        "expect_text": ["Local page"]}])
                self.assertEqual(plan[0]["path"], path)
                target = urlsplit(base + plan[0]["path"])
                self.assertEqual((target.scheme, target.netloc), ("http", "127.0.0.1:33141"))

    def test_navigation_still_rejects_remote_relative_or_control_addresses(self):
        for path in ("https://example.test/#/route", "//example.test/#/route",
                     "///example.test", "javascript:alert(1)", "data:text/html,x",
                     "#/signin", "settings", "/\\example.test", "/#\\example.test",
                     "/\n/evil", "/\r/evil", "/\t/evil"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_steps([{"action": "navigate", "path": path}])

    def test_navigation_forwards_exact_route_and_assertions(self):
        page = Mock()
        step = validate_steps([{"action": "navigate", "path": "/#/settings",
            "expect_text": ["Settings"], "expect_absent": ["Signed out"],
            "expect_scope": {"role": "main"}}])[0]
        _perform(page, step, "http://127.0.0.1:33141")
        page.goto.assert_called_once_with("http://127.0.0.1:33141/#/settings",
            wait_until="domcontentloaded", timeout=10000)
        self.assertEqual(validate_steps([step]), [step])
        self.assertEqual(step["expect_text"], ["Settings"])
        self.assertEqual(step["expect_scope"], {"role": "main"})


if __name__ == "__main__":
    unittest.main()
