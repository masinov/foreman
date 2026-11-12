"""The built dashboard bundle is not in git: it is built when needed."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from foreman import dashboard_runtime
from foreman.dashboard_runtime import (
    MISSING_BUNDLE_MESSAGE,
    build_dashboard_assets,
    dashboard_bundle_is_stale,
)


class BundleFreshnessTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "frontend"
        (self.source / "src").mkdir(parents=True)
        (self.source / "package.json").write_text("{}")
        (self.source / "src" / "main.jsx").write_text("//")
        self.index = self.root / "dist" / "index.html"

    def _build(self) -> None:
        self.index.parent.mkdir(exist_ok=True)
        self.index.write_text("<div id=root></div>")

    def test_no_bundle_is_stale(self) -> None:
        self.assertTrue(dashboard_bundle_is_stale(self.source, self.index))

    def test_a_bundle_built_after_the_source_is_current(self) -> None:
        self._build()
        future = time.time() + 60
        os.utime(self.index, (future, future))
        self.assertFalse(dashboard_bundle_is_stale(self.source, self.index))

    def test_a_source_file_changed_after_the_build_makes_it_stale(self) -> None:
        self._build()
        future = time.time() + 60
        os.utime(self.source / "src" / "main.jsx", (future, future))
        self.assertTrue(dashboard_bundle_is_stale(self.source, self.index))

    def test_an_installed_package_without_source_is_never_stale(self) -> None:
        self._build()
        self.assertFalse(dashboard_bundle_is_stale(self.root / "no-source", self.index))


class BuildTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.source = Path(temp.name)

    def test_installs_dependencies_first_when_there_are_none_then_builds(self) -> None:
        calls: list[list[str]] = []

        def run(command, **kwargs):
            calls.append(command[1:])
            self.assertEqual(kwargs["cwd"], str(self.source))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        build_dashboard_assets(self.source, run=run, which=lambda _: "/usr/bin/npm", announce=lambda _: None)

        self.assertEqual(calls, [["ci"], ["run", "build"]])

    def test_only_builds_when_dependencies_are_installed(self) -> None:
        (self.source / "node_modules").mkdir()
        calls: list[list[str]] = []

        def run(command, **kwargs):
            calls.append(command[1:])
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        build_dashboard_assets(self.source, run=run, which=lambda _: "/usr/bin/npm", announce=lambda _: None)

        self.assertEqual(calls, [["run", "build"]])

    def test_says_so_when_npm_is_missing(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "npm"):
            build_dashboard_assets(self.source, which=lambda _: None, announce=lambda _: None)

    def test_a_failed_build_reports_the_end_of_its_output(self) -> None:
        (self.source / "node_modules").mkdir()

        def run(command, **kwargs):
            return SimpleNamespace(returncode=1, stdout="building", stderr="error: missing module")

        with self.assertRaisesRegex(RuntimeError, "missing module"):
            build_dashboard_assets(self.source, run=run, which=lambda _: "/usr/bin/npm", announce=lambda _: None)


class PrepareTests(unittest.TestCase):
    def test_does_not_build_when_told_not_to(self) -> None:
        with mock.patch.dict(os.environ, {"FOREMAN_DASHBOARD_NO_BUILD": "1"}), mock.patch.object(
            dashboard_runtime, "build_dashboard_assets"
        ) as build, mock.patch.object(dashboard_runtime, "ensure_dashboard_assets"):
            dashboard_runtime.prepare_dashboard_assets()
        build.assert_not_called()

    def test_builds_a_stale_bundle_in_a_source_checkout(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False), mock.patch.object(
            dashboard_runtime, "dashboard_bundle_is_stale", return_value=True
        ), mock.patch.object(dashboard_runtime, "build_dashboard_assets") as build, mock.patch.object(
            dashboard_runtime, "ensure_dashboard_assets"
        ):
            os.environ.pop("FOREMAN_DASHBOARD_NO_BUILD", None)
            dashboard_runtime.prepare_dashboard_assets()
        build.assert_called_once()


class ShellWithoutBundleTests(unittest.TestCase):
    def test_the_api_works_and_the_shell_says_how_to_build(self) -> None:
        from fastapi.testclient import TestClient

        from foreman.dashboard.app import create_dashboard_app
        from foreman.store import ForemanStore

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db_path = str(Path(temp.name) / "foreman.db")
        store = ForemanStore(db_path)
        store.initialize()
        store.close()
        missing = Path(temp.name) / "nowhere" / "index.html"
        with mock.patch("foreman.dashboard.app.dashboard_assets_present", return_value=False), mock.patch(
            "foreman.dashboard.app.DASHBOARD_INDEX_PATH", missing
        ):
            client = TestClient(create_dashboard_app(db_path))
            shell = client.get("/dashboard")
            projects = client.get("/api/v1/projects")

        self.assertEqual(shell.status_code, 503)
        self.assertIn(MISSING_BUNDLE_MESSAGE.split(".")[0], shell.text)
        self.assertEqual(projects.status_code, 200)
