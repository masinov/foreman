# The independent review of sprint 68: the review sandbox and the database

- A branch under review can no longer configure its reviewer: the step loads no project settings and runs no hook, so a `.claude/settings.json` committed on the branch does nothing.
- An agent is never given the Claude Code session the engine was started from (`CLAUDE_CODE_MESSAGING_*`, `CLAUDE_CODE_SESSION_*`, `CLAUDECODE`, …), and a sandbox allowed unix sockets no longer opens `/run/user/<uid>/cc-socks`: a reviewer could talk to the operator's own session.
- Each sandboxed step has a short temporary directory of its own, removed with it; Claude Code's shared `/tmp/claude-<uid>` is closed to it.
- The database copy in a sandbox is opt-in (`sandbox_database_copy`) and holds only the project's own rows, without API tokens, notification destinations, the manager's conversations or leases, vacuumed.
- Codex: a role only not given Bash keeps the shell it reads with (read-only, asked about the rest); a Codex sandbox excludes the host's `/tmp`; `CODEX_*` keys are masked; `accept_open_reads` is never passed to Claude Code.
- A sandbox clone has the repository's git identity, is recognised as Foreman's without its marker, and the suite sets its own identity, so the tests pass inside a sandbox.
- `FOREMAN_DB` is never given to the test command, the worktree setup command or an agent, and a project cannot pass it through; `worktree_link_paths` refuses the database, `.foreman/` and `.git`; discovery stops at `.foreman/`, and in a worktree says the database is out of reach on purpose.
