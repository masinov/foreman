"""An installed Foreman carries what it needs, and states its version once."""

from __future__ import annotations

from pathlib import Path
import unittest


class PackagedDataTests(unittest.TestCase):
    """What an installed Foreman needs is inside the package."""

    def test_roles_workflows_and_templates_live_in_the_package(self) -> None:
        import foreman
        from foreman.data import ROLES_DIR, TEMPLATES_DIR, WORKFLOWS_DIR
        from foreman.roles import default_roles_dir, load_roles
        from foreman.workflows import default_workflows_dir, load_workflows

        package_dir = Path(foreman.__file__).resolve().parent
        for directory in (ROLES_DIR, WORKFLOWS_DIR, TEMPLATES_DIR):
            self.assertTrue(directory.is_dir(), directory)
            self.assertEqual(directory.parent.parent, package_dir)
        self.assertEqual(default_roles_dir(), ROLES_DIR)
        self.assertEqual(default_workflows_dir(), WORKFLOWS_DIR)
        roles = load_roles()
        self.assertGreaterEqual(len(roles), 7)
        self.assertGreaterEqual(len(load_workflows(available_role_ids=set(roles))), 4)

    def test_the_build_ships_every_data_file(self) -> None:
        import fnmatch

        import foreman
        from foreman._toml import load_toml_file

        repo_root = Path(foreman.__file__).resolve().parent.parent
        pyproject = load_toml_file(repo_root / "pyproject.toml")
        patterns = pyproject["tool"]["setuptools"]["package-data"]["foreman"]
        package_dir = repo_root / "foreman"
        data_files = [
            path.relative_to(package_dir).as_posix()
            for path in (package_dir / "data").rglob("*")
            if path.is_file() and path.suffix != ".py" and "__pycache__" not in path.parts
        ]

        self.assertTrue(data_files)
        unshipped = [
            name for name in data_files if not any(fnmatch.fnmatch(name, p) for p in patterns)
        ]
        self.assertEqual(unshipped, [])

    def test_the_version_is_stated_once(self) -> None:
        import foreman
        from foreman._toml import load_toml_file

        repo_root = Path(foreman.__file__).resolve().parent.parent
        pyproject = load_toml_file(repo_root / "pyproject.toml")

        self.assertNotIn("version", pyproject["project"])
        self.assertEqual(pyproject["project"]["dynamic"], ["version"])
        self.assertEqual(
            pyproject["tool"]["setuptools"]["dynamic"]["version"], {"attr": "foreman.__version__"}
        )
        self.assertTrue(foreman.__version__)


if __name__ == "__main__":
    unittest.main()
