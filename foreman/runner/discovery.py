"""Which agent backends this machine has, and the models Foreman asks them for.

Neither agent CLI can list the models it serves, so "the models a runner
offers" here means the models the role definitions name for that backend
(each role's ``model`` and its ``model_ladder``). A role whose model is empty
leaves the choice to the backend's own default, which is reported as
``uses_default`` rather than invented as a model name.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterable
from typing import Any

from .claude_code import ClaudeCodeRunner
from .codex import CodexRunner

#: ``(backend id as a role names it, name a person knows it by, runner class)``.
#: The backend ids are the keys the orchestrator registers its runners under.
BACKENDS: tuple[tuple[str, str, Any], ...] = (
    ("claude_code", "Claude Code", ClaudeCodeRunner),
    ("codex", "Codex", CodexRunner),
)


def describe_runners(
    roles: Iterable[Any],
    *,
    which: Callable[[str], str | None] = shutil.which,
) -> list[dict[str, Any]]:
    """Describe each backend: where its program is, and the models roles use on it.

    ``roles`` are role definitions (``foreman.roles.RoleDefinition``). A backend
    is "found" when its executable resolves on ``PATH``; nothing is launched.
    """

    roles = list(roles)
    described: list[dict[str, Any]] = []
    for backend_id, name, runner_class in BACKENDS:
        executable = runner_class().executable
        path = which(executable)
        models: list[str] = []
        uses_default = False
        for role in roles:
            if role.agent.backend != backend_id:
                continue
            for model in (role.agent.model, *role.agent.model_ladder):
                if not model:
                    uses_default = True
                elif model not in models:
                    models.append(model)
        described.append(
            {
                "id": backend_id,
                "name": name,
                "executable": executable,
                "found": path is not None,
                "path": path,
                "models": models,
                "uses_default": uses_default,
            }
        )
    return described


