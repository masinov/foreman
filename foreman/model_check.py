"""Ask an agent program whether it can run a model, before a role is saved with it.

A role's model is handed to the agent program unchanged. An id the program
cannot run used to be saved without a word and found out only when a task
reached the role, as a run that did nothing. The only one who knows which
models work on this machine (its account, its version, a gateway it may be
pointed at) is the program itself, so it is asked: one short question to the
model. A model that does not exist is refused in about two seconds at no
cost; one that exists answers for a fraction of a cent.

Claude Code is checked. Codex is not yet: nothing here has been tried
against it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

#: Set to ``off`` to save a role without asking (a machine with no network).
SWITCH = "FOREMAN_MODEL_CHECK"
_TIMEOUT_SECONDS = 90


def check_model(backend: str, model: str) -> str | None:
    """Return why ``backend`` cannot run ``model``, or ``None``.

    ``None`` also when the question could not be put: the program is not on
    this machine, it did not answer in time, or it answered something this
    does not understand. A save is refused only on the program's own word.
    """

    if not model or backend != "claude_code" or os.environ.get(SWITCH, "").lower() == "off":
        return None
    executable = shutil.which("claude")
    if executable is None:
        return None
    try:
        done = subprocess.run(
            [executable, "--model", model, "-p", "Reply with the word ok.", "--tools", "", "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        answer = json.loads(done.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    if not isinstance(answer, dict) or not answer.get("is_error"):
        return None
    said = str(answer.get("result") or "").strip() or "it gave no reason"
    return f"Claude Code cannot run the model {model!r} on this machine. It says: {said}"
