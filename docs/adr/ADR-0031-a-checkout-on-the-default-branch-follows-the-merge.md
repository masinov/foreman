# ADR-0031: A checkout on the default branch follows the merge

- **Status:** accepted
- **Date:** 2026-11-18
- **Sprint:** 60
- **Amends:** ADR-0012 ("What the operator's checkout does and does not see")

## Context

ADR-0012 put every merge in Foreman's own integration worktree and left the
operator's checkout alone. It accepted one consequence as irreducible: a
person sitting on the default branch sees the ref move under them, and their
files go on describing the commit before.

Assay, the first project run through Foreman that is not Foreman, showed
what that costs. Its folder was registered while on `main`, the default
branch. All nine tasks of its first sprint merged, and the owner opened the
folder and found none of the code. `git status` listed every merged file as
a staged deletion. A commit made there would have undone the whole sprint.
The only way out was a `git reset --hard` that the owner had to run
themselves.

A fresh repository is on its default branch, so this is the normal state of
a newly registered project, not an edge case.

## Decision

**After a successful merge, `_builtin:merge` brings the project's own
checkout to the merge commit when that checkout is on the default branch
and the update cannot lose anything.** It does what a fast-forward
`git pull` would have done there.

- **Which commit the checkout still shows** is read from its index: the
  index must equal the tree of a commit in the default branch's first-parent
  history (the last 1000). A checkout several merges behind is brought along
  in one step.
- **The update** is `git read-tree -m -u <shown> <merge>`. It keeps
  untracked files and unstaged edits. Where the update would overwrite one,
  it refuses and changes nothing.
- **What is left alone:** a checkout on any other branch, one with staged
  changes that are not a commit of the default branch, one with an
  unconcluded merge or conflicts, and one where `read-tree` refuses.
- **What is recorded:** `engine.checkout_updated` (path, branch, from_sha,
  sha) when the checkout was brought along, and `engine.checkout_behind`
  (path, branch, sha, reason) when it could not be. Nothing is recorded for
  another branch or a checkout that already shows the merge. The merge stands
  whatever happens to the checkout.

## Consequences

- A person who registers a project and stays on its default branch sees each
  merged task in their folder, as they would after pulling.
- ADR-0012's rule now reads: the engine never checks out, merges or resets
  in the operator's checkout. It may move a checkout on the default branch
  forward along that branch. It never touches a person's own edits to do so.
- A person working on their own branch, as Foreman's own repository does
  (`chore/operator-checkout`), is unaffected.
- A person who is editing on the default branch while the engine merges can
  see files change under them. That was already true of the ref, and the
  edits themselves are kept or the update is refused.

## Alternatives considered

- **Move the checkout off the default branch when the project is
  registered.** This changes the person's branch without being asked, and
  they still have to merge by hand to see any work.
- **Refuse to start the engine while the checkout is on the default branch.**
  This makes every new project fail on its first run with a git chore.
- **`git reset --hard` to the merge.** This would discard a person's edits.
