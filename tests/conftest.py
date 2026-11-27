"""Suite-wide guard: no test leaves an asyncio loop running on its worker.

A running loop is per thread. If one stays set after a test, every later
``asyncio.run()`` on that pytest-xdist worker fails with "asyncio.run() cannot
be called from a running event loop", and the failure lands on an innocent
test (FOR-66). The pytest-playwright plugin does this: its sync API keeps a
loop running on the main thread. This guard fails the test that leaves one,
by name, instead of a bystander.
"""

from __future__ import annotations

import asyncio
import os

import pytest

#: Variables that change what git does. A suite started inside something that
#: sets them (a review sandbox with a push guard in ``GIT_CONFIG_PARAMETERS``)
#: would have its throwaway repositories pick them up: a test's own push hit
#: the guard's hook and was read as the reviewer's push. Removed before any
#: test, in every worker, so the tests see only the git they make themselves.
GIT_ENVIRONMENT_EXACT = frozenset(
    {
        "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT", "GIT_CONFIG", "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM", "GIT_DIR", "GIT_WORK_TREE",
        "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CEILING_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE", "GIT_PREFIX",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM", "GIT_EXEC_PATH", "GIT_TEMPLATE_DIR",
        "GIT_SSH", "GIT_SSH_COMMAND", "GIT_ASKPASS", "GIT_REPLACE_REF_BASE",
        "GIT_NO_REPLACE_OBJECTS", "GIT_SHALLOW_FILE", "GIT_QUARANTINE_PATH",
    }
)
GIT_ENVIRONMENT_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")


def scrub_git_environment(environ: "os._Environ[str] | dict[str, str]") -> None:
    for name in list(environ):
        if name in GIT_ENVIRONMENT_EXACT or name.startswith(GIT_ENVIRONMENT_PREFIXES):
            del environ[name]


scrub_git_environment(os.environ)

# Browser tests run only with the plugin on (``-o addopts=""``), and it keeps a
# loop running by design; they are run on their own (docs/TESTING.md).
_BROWSER_TESTS = "test_e2e.py"


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


@pytest.fixture(autouse=True)
def no_asyncio_loop_is_left_running(request: pytest.FixtureRequest):
    # A loop already running when the test began was left by another one
    # (a browser test, or one already failed): this test is not blamed.
    before = _running_loop()
    yield
    if request.node.nodeid.split("::")[0].endswith(_BROWSER_TESTS):
        return
    loop = _running_loop()
    if loop is None or loop is before:
        return
    # Cleared, so the tests after this one on the worker run as usual.
    asyncio.events._set_running_loop(None)
    pytest.fail(f"this test left an asyncio loop running on its worker: {loop!r}", pytrace=False)
