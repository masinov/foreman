"""The suite does not depend on the git environment it is started in."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.conftest import scrub_git_environment

ROOT = Path(__file__).resolve().parent.parent


class ScrubTests(unittest.TestCase):
    def test_the_variables_that_change_git_are_removed_and_others_stay(self) -> None:
        env = {
            "GIT_CONFIG_PARAMETERS": "'a=b'", "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "k",
            "GIT_CONFIG_VALUE_0": "v", "GIT_DIR": "/x", "GIT_WORK_TREE": "/y",
            "GIT_INDEX_FILE": "i", "GIT_OBJECT_DIRECTORY": "o",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": "a", "GIT_CEILING_DIRECTORIES": "c",
            "GIT_EDITOR": "true", "PATH": "/bin",
        }
        scrub_git_environment(env)
        self.assertEqual(env, {"GIT_EDITOR": "true", "PATH": "/bin"})


class PushGuardEnvironmentTests(unittest.TestCase):
    def test_a_suite_started_under_a_push_guard_passes_and_leaves_no_mark(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            guard = Path(raw)
            mark = guard / "push-attempted"
            hook = guard / "hooks" / "pre-push"
            hook.parent.mkdir()
            hook.write_text(f"#!/bin/sh\necho pushed > '{mark}'\nexit 1\n")
            hook.chmod(0o755)
            sink = guard / "sink.git"
            subprocess.run(["git", "init", "--bare", "--quiet", str(sink)], check=True)
            env = {
                **os.environ,
                "GIT_CONFIG_PARAMETERS": (
                    f"'remote.origin.pushurl={sink}' 'core.hookspath={guard / 'hooks'}'"
                ),
            }
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                 "tests/test_sandbox.py", "tests/test_worktrees.py"],
                cwd=ROOT, env=env, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr[-1000:])
            self.assertFalse(mark.exists(), "a test's push reached the guard's hook")


if __name__ == "__main__":
    unittest.main()
