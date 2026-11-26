"""The version a person decides on at a human gate.

An acceptance names what it accepted. A merge approval is of the task
branch's head commit, and of the default branch's head it would merge into;
a plan approval is of the task's description and criteria as they stand,
and of the run whose plan it is. A decision is recorded against the version
current at that moment; a decision that names the version the person saw is
refused when it is no longer current.

The plan's fingerprint covers the run as well as the text: a plan redone by
a new run with the same words is a different version.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

MERGE_APPROVAL = "merge_approval"
PLAN_APPROVAL = "plan_approval"

#: Fewest characters of a commit that identify it, when a person types it short.
MIN_SHA_PREFIX = 7

_HEX = re.compile(r"^[0-9a-f]+$")


@dataclass(frozen=True)
class GateVersion:
    """What is in front of a person at a gate, at one moment."""

    kind: str | None = None  # merge_approval, plan_approval, or None (another gate)
    branch_sha: str | None = None
    base_sha: str | None = None
    fingerprint: str | None = None
    plan_run_id: str | None = None

    @property
    def token(self) -> str | None:
        """The one value a request names to say which version it saw."""

        if self.kind == MERGE_APPROVAL:
            return self.branch_sha
        if self.kind == PLAN_APPROVAL:
            return self.fingerprint
        return None

    @property
    def short(self) -> str | None:
        """The version in the words of a line: a short commit, or a short fingerprint."""

        token = self.token
        return token[:7] if token else None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "kind": self.kind,
            "branch_sha": self.branch_sha,
            "base_sha": self.base_sha,
            "fingerprint": self.fingerprint,
            "plan_run_id": self.plan_run_id,
            # The one value a request names (``token``), so a client need not
            # know which field it is.
            "token": self.token,
        }


def plan_fingerprint(
    description: str | None, criteria: str | None, plan_run_id: str | None = None
) -> str:
    """A fingerprint of a plan: the task's description and criteria, and the run that wrote it."""

    text = f"{(description or '').strip()}\n\x00\n{(criteria or '').strip()}"
    if plan_run_id:
        text += f"\n\x00\n{plan_run_id}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def malformed_version(seen: str, current: GateVersion) -> str | None:
    """Why a version a request names cannot name any version of this gate, or None.

    A version is a commit or a fingerprint: hexadecimal, at least
    ``MIN_SHA_PREFIX`` characters. A gate with nothing to name (no policy
    with a version, or a branch whose head cannot be read) takes none.
    """

    seen = seen.strip().lower()
    if current.kind is None:
        return "This gate has no version to name; approve it without one."
    if current.token is None:
        what = "branch head" if current.kind == MERGE_APPROVAL else "plan"
        return f"The {what} could not be read, so there is no version to name; approve it without one."
    if len(seen) < MIN_SHA_PREFIX:
        return (
            f"A version names at least {MIN_SHA_PREFIX} characters of the commit or "
            f"fingerprint; {seen!r} is too short."
        )
    if not _HEX.match(seen):
        return f"A version is a commit or a fingerprint (0-9, a-f); {seen!r} is not one."
    return None


def names_current(seen: str, current: str | None) -> bool:
    """Whether a version a request names (whole, or a prefix of 7 or more) is the current one."""

    seen = seen.strip().lower()
    if not current or len(seen) < MIN_SHA_PREFIX:
        return False
    return current.lower().startswith(seen)
