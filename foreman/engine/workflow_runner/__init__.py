"""Walking a task through its workflow, one step at a time.

``WorkflowRunner.run_from_step`` runs a task from a step until it stops:
done, blocked, paused at a human gate, cancelled by an operator, or waiting
for a quota to reset. One pass of the loop is one step, and each part of a
step is a method: check the task is still the engine's to work on, check its
worktree and its limits, refresh its branch, run the step (a human gate, a
built-in, or an agent), record what happened, and follow the transition.

The step loop, in one part per concern:

- ``base``: the loop itself and what it reads and writes between steps,
- ``checks``: what is checked before a step (the worktree, the branch, the
  limits),
- ``builtin_steps``: a human gate and a built-in step,
- ``agent_steps``: an agent's step and what its run says,
- ``transitions``: recording a step's end and following the workflow on.
"""

from __future__ import annotations

from .agent_steps import AgentSteps
from .builtin_steps import BuiltinSteps
from .checks import StepChecks
from .transitions import Transitions

__all__ = ["WorkflowRunner"]


class WorkflowRunner(
    StepChecks,
    BuiltinSteps,
    AgentSteps,
    Transitions,
):
    """Walk one task through its workflow, a step at a time."""
