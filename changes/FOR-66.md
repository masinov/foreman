# A test that leaves an asyncio loop running is named, not blamed on a later one

- The intermittent `asyncio.run() cannot be called from a running event loop` failures in `tests/test_meta_agent.py` came from the pytest-playwright plugin, whose sync API keeps a loop running on the worker's main thread (fixed by turning it off by default, 5cb1e2a).
- `tests/conftest.py` now fails the test that leaves a loop running, by name, so a leak can no longer land on an unrelated test.
