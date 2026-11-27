# ADR-0044: The Reviewer Runs In The Backend's Sandbox, In Its Own Clone

- **Status:** accepted (owner, 2026-11-27: "fix them now"; the survey and the
  probe on this machine, Ubuntu 20.04, bubblewrap 0.4.0, socat, Claude Code
  2.1.332, by Claude)
- **Date:** 2026-11-27
- **Amends:** ADR-0041 section 5 (run scope: what a `sandbox` role is kept
  from, and how)

## Context

ADR-0041 section 5 gave the code reviewer a throwaway worktree, a check on the
task's branch and a push guard made of git settings in the step's environment
(FOR-75). The independent review of sprint 67 found that this was a deterrent:
the reviewer runs as the operator with Bash, so `env -u GIT_CONFIG_PARAMETERS
git push origin ...` or `git -c remote.origin.pushurl=<real> push` reached the
real remote with the operator's credentials (checked against a local bare
remote). The worktree shares `.git` with the main checkout, so other refs and
the repository config could be changed and only the task branch was checked.
On Codex, `run_scope = "none"` was not enforced: Codex ran commands in its own
sandbox without asking.

Survey (owner, 2026-11-18: prefer integrating mature tools): Claude Code's own
sandbox (bubblewrap, a network allowlist, `allowUnsandboxedCommands = false`),
bubblewrap or a separate user used directly, and Codex's sandbox modes. A probe
of Claude Code's sandbox on this machine found: a push outside the working
directory and a write outside it fail (read-only file system); https to
`github.com` is refused by its proxy, also with the proxy variables unset; a
local HTTP server and a request to it work in one command; reads are open
except what is denied, so `~/.ssh` is readable unless the home directory is
denied; the Read, Grep and Glob tools are not covered by the sandbox and follow
permission rules instead.

## Decision

1. **Use Claude Code's sandbox, passed per run with `claude --settings`.**
   Foreman builds none of its own. A sandboxed step runs with
   `failIfUnavailable` and `allowUnsandboxedCommands = false`: a machine
   without `bwrap` and `socat` fails the step with the reason (Foreman checks
   first and names what is missing), and a command never runs outside the
   sandbox.
2. **What it is kept from.** Writes: everywhere but its own working copy.
   Network: every host but the project's `sandbox_allowed_hosts` (empty by
   default; `localhost` works). Reads: the operator's home directory and the
   directory the repository sits in (other projects), except the step's
   working copy, the repository's `.git/objects`, what `worktree_link_paths`
   links in and the project's `sandbox_read_paths`. The Read, Grep and Glob
   tools get permission rules for the same paths, listed entry by entry because
   a deny rule wins over an allow. The backend keys in the step's environment
   (`ANTHROPIC_*`, `OPENAI_*`, `CLAUDE_CODE_OAUTH*`) are masked from commands
   with `sandbox.credentials`.
3. **Unix sockets are opt-in** (`sandbox_allow_unix_sockets`, default off). A
   browser needs one for its profile lock, and the screenshots script needs a
   browser. Allowing sockets lets a command connect to any socket it can see:
   the probe reached the user's session bus, an escape (it starts processes
   outside the sandbox). So when it is on, `/run`, `/tmp` and `/var/tmp` are
   closed to commands (a socket file cannot be hidden alone, a directory can)
   except what Claude Code's own sandbox needs there, and the probe then could
   not reach the session bus, the system bus, the container engine or X.
4. **The sandbox is its own clone** of the commit under review (`git clone
   --shared`: objects shared, no remote, its own refs and config), not a linked
   worktree. A linked worktree writes the main repository's refs (Claude Code's
   sandbox allows it, to make git work); a clone cannot reach them. The branch
   check stays: the task's branch is compared with its head when the sandbox
   opened, put back if it moved, and the step fails. The environment push guard
   (`_no_push_env`, `GIT_CONFIG_PARAMETERS`) goes: nothing needs it.
5. **The reviewer is given a snapshot of the database** at `.review/live.db`
   (SQLite backup), since it cannot read the main checkout where the live one
   is; `scripts/review_screenshots.py` reads it.
6. **Codex.** A sandboxed step runs in Codex's `workspace-write` sandbox in the
   clone without network, with approval policy `never`, and every approval
   request is declined. A role that runs no command (`run_scope = "none"`, or
   no command tool) gets a `read-only` sandbox without network, approval policy
   `untrusted` (it asks about each command) and the shell tools off; Foreman
   declines each request. Foreman reads back what the app server applied
   (`thread/start` answers with the sandbox and approval policy) and fails the
   step if it is not what was asked. What Codex cannot enforce, reads of the
   home directory, credentials and other projects, makes Foreman **refuse a
   `sandbox` role on Codex at load**, naming why; a role accepts the open reads
   with `accept_open_reads = true` under `[agent.flags]`.
7. **Out of scope:** the developer step still runs as the operator,
   unsandboxed. The MANUAL says so; sandboxing it is a separate task.

## Consequences

- A reviewer of a project needs its toolchain readable: a Python or Node
  installed under the home directory, or the base interpreter a setup-command
  venv points to, goes into `sandbox_read_paths`. A path linked with
  `worktree_link_paths` is read-only to the step: a build that writes into it
  (Vite writes `node_modules/.vite-temp`) fails; the project builds its own in
  `worktree_setup_command`, which runs outside the sandbox with network.
- Everything the reviewer may read is in its context, so with the model
  provider: do not list a secret.
- The sandbox depends on Claude Code's. A change to its settings names, or to
  how it orders its mounts, is found by the probe in this task's report and by
  the settings tests, not by a unit test of bubblewrap.
- Codex's enforcement of a command (the shell tools off, the approval policy)
  was checked for what the app server applies, not by a model running a
  command: the engine's Codex login was refused when this was written (401).
- Landlock or a separate user would be stronger than a mount namespace in some
  respects; they were not chosen because Claude Code's sandbox is maintained
  and already integrated with the tools.
