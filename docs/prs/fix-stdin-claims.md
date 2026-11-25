# PR Summary: fix/stdin-claims

## Summary

- An independent review of FOR-60 found that its claim was false. FOR-60
  said a command that reads standard input gets end-of-file at once.
  - Claude Code gives a plain command `/dev/null`.
  - A command that also holds a heredoc gets a socket, and a read waits
    for the 20-minute Bash timeout. That is the shape of the runs behind
    the FOR-53 stall.
- `docs/ARCHITECTURE.md` and the developer prompt now say what is true. The
  prompt tells the agent to give every input explicitly.
- The candidate fix is not made here: wrapping each command through Claude
  Code's shell prefix with `< /dev/null`. It needs a live probe of Claude
  Code, which the permission check refused. It is in the backlog for the
  owner.
- The backlog gains "Found while reviewing sprint 63", listing the reviews'
  findings that are not fixed yet.

## Scope

The developer prompt, ARCHITECTURE.md, the backlog, the sprint file.

## Files changed

- `foreman/data/roles/developer.toml`
- `docs/ARCHITECTURE.md`
- `docs/sprints/backlog.md`
- `docs/sprints/current.md`
- this note.

## Migrations

None.

## Risks

None; no behaviour changes in code.

## Tests

- The prompt tests (`tests/test_engine_prompts.py`) and the whole suite.

## Acceptance criteria

- No document or prompt claims a read gets end-of-file when it may not.

## Follow-ups

- In the backlog, "Found while reviewing sprint 63".
