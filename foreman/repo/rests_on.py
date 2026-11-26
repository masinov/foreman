"""Naming the documents a task rests on: each is checked against the default
branch, and the branch's commit at that moment is recorded with it.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ..domain.rests_on import DocumentRef, RestsOnError, parse_documents
from .git import run_git


def name_documents(
    repo_path: str | Path,
    default_branch: str,
    wanted: object,
    already: Iterable[DocumentRef] = (),
) -> list[DocumentRef]:
    """The documents of ``wanted`` (see ``parse_documents``) with their commits.

    A document that ``already`` names keeps its recorded commit: it was named
    then, not now. A new one gets the default branch's commit now, and its path
    must be a file there; one that is not is refused with the reason. Nothing is
    read from the working tree: the default branch is what the work rests on.
    """

    entries = parse_documents(wanted)
    kept = {ref.key: ref for ref in already}
    new = [entry for entry in entries if entry.key not in kept]
    commit = ""
    if new:
        head = run_git(repo_path, "rev-parse", "--verify", f"{default_branch}^{{commit}}", check=False)
        if head.returncode != 0:
            raise RestsOnError(
                f"The default branch {default_branch!r} has no commit in {repo_path}, "
                "so there is nothing to name a document at."
            )
        commit = head.stdout.strip()
    named: list[DocumentRef] = []
    for entry in entries:
        if entry.key in kept:
            named.append(kept[entry.key])
            continue
        kind = run_git(repo_path, "cat-file", "-t", f"{commit}:{entry.path}", check=False)
        if kind.returncode != 0:
            raise RestsOnError(
                f"{entry.path} does not exist on {default_branch} (at {commit[:8]}); "
                "name a file that is committed there."
            )
        if kind.stdout.strip() != "blob":
            raise RestsOnError(f"{entry.path} is a directory on {default_branch}; name a file in it.")
        named.append(DocumentRef(entry.path, entry.heading, commit))
    return named
