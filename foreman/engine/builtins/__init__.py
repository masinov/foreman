"""Built-in workflow step executors for Foreman.

One part per built-in step, composed into ``BuiltinExecutor``:

- ``base``: dispatching a role to its step, the human gate, writing context,
- ``run_tests``: the project's test command, in the task's worktree,
- ``merge``: merging a task's branch, and bringing a branch that is behind up
  to date first (ADR-0026, ADR-0031),
- ``completion``: the completion guard, which decides from the evidence
  whether a task may merge (ADR-0018), and merge waivers,
- ``done``: marking a task done and removing its worktree.
"""

from __future__ import annotations

from .completion import CompletionGuard
from .done import MarkDoneStep
from .merge import MergeStep
from .run_tests import RunTestsStep

__all__ = ["BuiltinExecutor"]


class BuiltinExecutor(
    RunTestsStep,
    MergeStep,
    CompletionGuard,
    MarkDoneStep,
):
    """Execute built-in Foreman workflow roles."""
