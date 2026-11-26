"""Naming the documents a task rests on: each is checked against the default
branch, and the branch's commit at that moment is recorded with it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from ..domain.rests_on import DocumentRef, RestsOnError, parse_documents, parse_entry
from .git import GitCommandResult, run_git

#: Tree entry modes git gives a file that is a document: a regular file,
#: executable or not. A symbolic link (120000), a directory (040000) and a
#: submodule (160000) are not.
_FILE_MODES = frozenset({"100644", "100755"})


def _git(repo_path: str | Path, *args: str) -> GitCommandResult:
    """One git command in the project's repository, or ``RestsOnError`` saying why it cannot run."""

    if not Path(repo_path).is_dir():
        raise RestsOnError(
            f"The project's repository {repo_path} does not exist on this machine, "
            "so no document can be checked."
        )
    try:
        return run_git(repo_path, *args, check=False)
    except OSError as exc:
        raise RestsOnError(f"git could not run in {repo_path}: {exc}") from exc


def default_branch_commit(repo_path: str | Path, default_branch: str) -> str:
    """The commit the default branch points at now, or ``RestsOnError`` saying why there is none."""

    head = _git(repo_path, "rev-parse", "--verify", "--quiet", f"refs/heads/{default_branch}^{{commit}}")
    if head.returncode != 0 or not head.stdout.strip():
        raise RestsOnError(
            f"The default branch {default_branch!r} has no commit in {repo_path} "
            "(or it is not a git repository), so there is nothing to name a document at."
        )
    return head.stdout.strip()


def _mode_at(repo_path: str | Path, commit: str, path: str) -> str | None:
    """The tree mode of ``path`` at ``commit``, or None when there is nothing there."""

    listed = _git(repo_path, "--literal-pathspecs", "ls-tree", "-z", "--full-tree", commit, "--", path)
    if listed.returncode != 0:
        return None
    for record in listed.stdout.split("\0"):
        meta, _, name = record.partition("\t")
        if name == path:
            return meta.split(" ", 1)[0]
    return None


def check_document(repo_path: str | Path, default_branch: str, commit: str, ref: DocumentRef) -> None:
    """Refuse, with the reason, a path that is not a plain file at ``commit``."""

    mode = _mode_at(repo_path, commit, ref.path)
    if mode is None:
        hint = ""
        if ref.heading and _mode_at(repo_path, commit, f"{ref.path}#{ref.heading}") is not None:
            whole = f"{ref.path}#{ref.heading}"
            hint = f" To name {whole}, write `{whole} #`: a space before the # that starts a heading."
        raise RestsOnError(
            f"{ref.path} does not exist on {default_branch} (at {commit[:8]}); "
            f"name a file that is committed there.{hint}"
        )
    if mode == "040000":
        raise RestsOnError(f"{ref.path} is a directory on {default_branch}; name a file in it.")
    if mode == "120000":
        raise RestsOnError(
            f"{ref.path} is a symbolic link on {default_branch}; name the file it points to."
        )
    if mode not in _FILE_MODES:
        raise RestsOnError(f"{ref.path} is not a file on {default_branch} (a submodule?); name a file.")


def name_documents(
    repo_path: str | Path,
    default_branch: str,
    wanted: object,
    already: Iterable[DocumentRef] = (),
) -> list[DocumentRef]:
    """The documents of ``wanted`` (see ``parse_documents``) with their commits.

    A document that ``already`` names keeps its recorded commit: it was named
    then, not now. So does a new heading of a path ``already`` names: changing
    which part of a document is meant is not reading it again (a restamp is
    ``restamp_document``). An entry of ``wanted`` given as a ``DocumentRef``
    that carries a commit was stamped by Foreman before (a manager's proposal,
    when it was made) and keeps it; text and mappings never bring a commit in.
    A new one gets the default branch's commit now, and its path must be a
    plain file there; one that is not is refused with the reason. Nothing is
    read from the working tree: the default branch is what the work rests on.
    """

    entries = parse_documents(wanted)
    kept = {ref.key: ref for ref in already}
    by_path: dict[str, str] = {}
    for ref in kept.values():
        by_path.setdefault(ref.path, ref.commit)
    if isinstance(wanted, Sequence) and not isinstance(wanted, str):
        for item in wanted:
            if isinstance(item, DocumentRef) and item.commit:
                stamped = parse_entry(item)
                kept.setdefault(stamped.key, stamped)
    new = [entry for entry in entries if entry.key not in kept and entry.path not in by_path]
    commit = default_branch_commit(repo_path, default_branch) if new else ""
    named: list[DocumentRef] = []
    for entry in entries:
        if entry.key in kept:
            named.append(kept[entry.key])
        elif entry.path in by_path:
            named.append(DocumentRef(entry.path, entry.heading, by_path[entry.path]))
        else:
            check_document(repo_path, default_branch, commit, entry)
            named.append(DocumentRef(entry.path, entry.heading, commit))
    return named


def restamp_document(
    repo_path: str | Path, default_branch: str, documents: Sequence[DocumentRef], target: DocumentRef
) -> list[DocumentRef]:
    """``documents`` with the entry ``target`` names stamped at the default branch's commit now.

    That is how a person says they have read a document again after it
    changed. The file must still be a plain file there.
    """

    if all(ref.key != target.key for ref in documents):
        raise RestsOnError(f"{target.label()} is not a document this task rests on.")
    commit = default_branch_commit(repo_path, default_branch)
    check_document(repo_path, default_branch, commit, target)
    return [DocumentRef(ref.path, ref.heading, commit) if ref.key == target.key else ref for ref in documents]
