# PR Summary: fix/host-level-settings

## Summary

- Sprint 55 slice 2. Removes the dashboard API's control over what runs on
  the host, and makes worktree cleanup unable to delete anything but git
  worktrees of the project.
- Also carries the CI fix for the first failed run on GitHub.

## Scope

- `foreman/settings.py`: `HOST_LEVEL_SETTINGS`, `changed_host_level_settings`.
- `foreman/dashboard_service.py`: settings and role updates refuse host-level
  changes (403); role files validated before replacing; intake source URLs
  http(s) only; worktree payload carries `owned`.
- `foreman/worktrees.py`: `is_owned`; removal, prune and the live-tree limit
  skip directories that are not worktrees of this repository; the root is
  never removed.
- Frontend: test command, judge URL, judge key variable, role backend and
  permission mode are read-only with the terminal command shown.
- Not in scope: mandatory repository allowlist for project registration.

## Files changed

- `foreman/settings.py`, `foreman/dashboard_service.py`,
  `foreman/worktrees.py`
- `frontend/src/components.jsx`, `frontend/src/components.test.jsx`,
  `foreman/dashboard_frontend_dist/*`
- `tests/test_dashboard_safety.py`, `tests/test_dashboard.py`,
  `tests/test_worktrees.py`
- `.github/workflows/ci.yml`
- `docs/adr/ADR-0017-host-level-settings-are-operator-only.md`,
  `docs/adr/README.md`, `docs/MANUAL.md`, `docs/STATUS.md`,
  `docs/sprints/current.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- Anyone who set the test command or judge endpoint from the Settings screen
  must now use `foreman config`. The screen says so.
- A directory left under the worktree root by an older layout is no longer
  removed by prune.
- The role tests now run against a copy of `roles/`; they no longer touch
  the shipped files.

## Tests

- `python -m unittest discover -s tests`: 1012 pass, 1 skipped (11 new)
- `npm --prefix frontend test`: 51 pass (1 new); build clean
- `ruff check foreman tests scripts`: clean
- CI fix verified in a clean clone with a fresh 3.12 virtualenv: 1001 pass
  on `main` with setuptools installed, the reported failure without it.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- No API call can change a shell command, a storage path, the judge
  endpoint, or a role's backend or permission mode.
- Prune with `worktree_root` pointed at a directory of unrelated files
  deletes none of them.
- The Settings screen still saves everything else.

## Follow-ups

- Slice 3: cost control.
- Administrator role for host-level settings when identity exists.
