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

import pytest

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
