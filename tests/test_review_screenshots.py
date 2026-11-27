"""The screenshot script reaches the network the way a review sandbox allows."""

from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from unittest import mock

_SPEC = importlib.util.spec_from_file_location(
    "review_screenshots", Path(__file__).resolve().parent.parent / "scripts" / "review_screenshots.py"
)
review_screenshots = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(review_screenshots)  # type: ignore[union-attr]

PROXY_NAMES = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy")


class BrowserProxyTests(unittest.TestCase):
    def test_the_browser_uses_the_sandboxs_proxy_and_reaches_the_dashboard_directly(self) -> None:
        env = {k: v for k, v in os.environ.items() if k not in PROXY_NAMES}
        env["HTTPS_PROXY"] = "http://localhost:3128"
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                review_screenshots.browser_proxy(),
                {"server": "http://localhost:3128", "bypass": "127.0.0.1,localhost"},
            )

    def test_a_login_in_the_proxys_address_is_given_apart(self) -> None:
        env = {k: v for k, v in os.environ.items() if k not in PROXY_NAMES}
        env["HTTPS_PROXY"] = "http://srt.abc:s%3Acret@127.0.0.1:3128"
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                review_screenshots.browser_proxy(),
                {
                    "server": "http://127.0.0.1:3128",
                    "bypass": "127.0.0.1,localhost",
                    "username": "srt.abc",
                    "password": "s:cret",
                },
            )

    def test_without_a_proxy_the_browser_goes_direct(self) -> None:
        env = {k: v for k, v in os.environ.items() if k not in PROXY_NAMES}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertIsNone(review_screenshots.browser_proxy())


if __name__ == "__main__":
    unittest.main()
