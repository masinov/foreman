"""The resident engine: `foreman serve`.

``foreman run`` is a one-shot pass. It exits the moment no runnable task is
left, so work that arrives afterwards — from the dashboard, from the CLI, from
the intake API — waits until a person presses Run again. ``foreman serve`` is
the same engine kept resident: it runs a pass, and when the pass has nothing to
do it sleeps until the database changes or the poll interval elapses, then runs
another one.

Three properties make it safe to leave running unattended:

* **One engine per project.** The whole loop runs inside an
  :class:`~foreman.engine.lock.EngineLock`, so a second ``serve`` or a
  ``run`` on the same project is refused rather than allowed to race.
* **A failed task cannot stop the service.** A task whose execution raises is
  parked as ``blocked`` with an attention turn and the loop continues after a
  doubling backoff.
* **A stop is not a failure.** SIGTERM and SIGINT settle the active run as
  ``killed`` with the task resumable, release the lock, and exit 0.

Signals are a blunt control channel: they cannot say "run *that* task", they
cannot be queued for an engine that is not up yet, and they leave no record of
who asked. So the engine also consumes the ``engine_commands`` table — the
durable channel the CLI, the dashboard, and the intake API all write to. The
loop drains pending commands at the top of every pass, and supplies the
orchestrator with a ``command_poll`` callback so a ``pause`` or a ``stop_task``
reaches an agent step that may already be twenty minutes into its work.

The loop is a plain object with injectable clocks, so all of that is testable
without a subprocess. The CLI handler only parses arguments and maps
:class:`ServeResult` to an exit code.

In one part per concern:

- ``base``: the resident loop, attaching to a project, and its log,
- ``commands``: the engine command table: reading, applying and finishing
  commands (ADR-0011),
- ``waiting``: sleeping until the database changes or a command arrives,
- ``serve``: ``serve_project``, what ``foreman serve`` runs.
"""

from __future__ import annotations

from .commands import CommandHandling
from .waiting import Waiting

__all__ = ["ResidentEngine"]


class ResidentEngine(
    CommandHandling,
    Waiting,
):
    """One project's engine, kept resident: passes, commands and waits."""
