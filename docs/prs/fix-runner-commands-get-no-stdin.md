# PR Summary: fix/runner-commands-get-no-stdin

## Summary

- Every command a Claude Code step runs now has `/dev/null` as standard
  input. Before, Claude Code gave a command that holds a heredoc a socket,
  and a read in it waited for the 20-minute Bash timeout: the FOR-53 stall,
  which FOR-60 did not fix (see `fix-stdin-claims.md`).
- The runner sets `CLAUDE_CODE_SHELL_PREFIX` to a shipped script,
  `foreman/data/shell/no-stdin.sh`. Claude Code passes it the whole command
  as one argument, and the script runs that with `bash -c` (or `zsh -c`)
  and `< /dev/null`.
- The step stops in preflight when the script is missing or not
  executable, since every command would fail through it. A role can opt
  out by setting the variable to an empty string.
- The developer prompt, `docs/ARCHITECTURE.md`, the changelog, the backlog
  and the sprint file say so.

## How it was checked live (2026-11-25, owner's approval)

Claude Code 2.1.332, `--print --model haiku --allowedTools Bash`, asked to
run one command that writes a heredoc to a file, then records
`readlink /proc/self/fd/0` and runs `timeout 15 cat`:

| Run | Standard input of the command | `cat` |
|---|---|---|
| without a prefix | `socket:[31866637]` | waited, killed by `timeout` (exit 124) |
| with the script | `/dev/null` | returned at once (exit 0) |

The heredoc wrote its file in both. A second run with two commands showed
that quoting (`'`, `$((…))`, an escaped `$HOME`), a `cd` carried to the next
command and an environment variable all come through unchanged.

Two shapes did not work, and are why the script looks as it does:
- `exec "$@" < /dev/null`: the single argument is the whole command line,
  so it is not a program name (exit 127).
- A prefix of `/bin/bash <script>`: Claude Code takes the prefix as one
  path (exit 127). So the file needs its executable bit.

## Scope

The Claude Code runner's step environment. The manager's session and the
Codex backend are unchanged; Codex is still not verified.

## Files changed

- `foreman/data/shell/no-stdin.sh` (new, mode 755)
- `foreman/runner/claude_code.py`: `NO_STDIN_PREFIX`, the variable in
  `HEADLESS_STEP_ENV`, `_check_shell_prefix` before launch
- `pyproject.toml`: the script is package data
- `tests/test_runner_claude.py`: four tests
- `foreman/data/roles/developer.toml`
- `docs/ARCHITECTURE.md`, `CHANGELOG.md`, `docs/sprints/backlog.md`,
  `docs/sprints/current.md`, `docs/STATUS.md`
- this note.

## Migrations

None.

## Risks

- A future Claude Code that calls the prefix differently would fail every
  command, visibly (exit 127 on each), not silently. The test that runs the
  script itself does not cover Claude Code's side; the live probe above
  does, for 2.1.332.
- A wheel install that drops the executable bit stops steps in preflight
  with a clear message. The editable install used here keeps git's mode.

## Tests

- `./venv/bin/python -m pytest tests/test_runner_claude.py -q`
- the whole suite, and the linters, before merge.

## Acceptance criteria satisfied

- A command that holds a heredoc and reads standard input returns at once
  under Claude Code (live probe, and the subprocess test with an open pipe).

## Follow-ups

- Verify Codex's standard input for commands.
