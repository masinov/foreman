# Sprint 49 — Review Phase 2 Manager Hardening

- **Branch:** `feat/meta-agent-persistence`
- **Merged:** 2026-06-13 (fast-forward to `main` at `62c2e25`, as part of the
  stacked review roadmap)
- **Status:** done

## Goal

Persist meta-agent sessions and turns, rebuild compact manager state on every
turn, make the manager contract honest through the CLI gaps, and preserve chat
history across dashboard restarts.

## Tasks completed

| # | Task | Deliverable |
|---|------|-------------|
| 1 | Migration 11 | `meta_sessions`, `meta_turns`, `idx_meta_turns_project`; applies cleanly on fresh and existing DBs |
| 2 | Store methods | `get_meta_session`, `save_meta_session`, `append_meta_turn`, `list_meta_turns` (oldest-first with `has_more` cursor paging), `clear_meta_session` |
| 3 | Store-backed meta agent | Dropped in-memory `_sessions`; session id + history from SQLite; assistant turn persisted in a `finally` path (flagged `interrupted` on error/cancel) so a crash never drops a turn; `--model` from `meta_agent_model` setting |
| 4 | Compact state header | `build_state_header()` regenerates a fixed-format world snapshot each turn (project/workflow/autonomy, sprint list with task counts, active-sprint task table with 80-char blocked-reason truncation, pending gates, last 5 noteworthy events) with a "trust this over your memory" disclaimer |
| 5 | Operating contract | `build_operating_contract()` enumerates the manager's exact CLI surface and hard rules on the first turn (re-injected after `clear_session`) |
| 6 | History pagination | Dashboard `meta/history` supports `limit`/`before`/`has_more`; `meta/message` keeps the store open for the full streaming turn |
| 7 | CLI task creation | `foreman task add` gained `--description`, `--sprint SPRINT_ID`, `--depends-on` (comma-separated, validated to exist in the same project) |

## Files changed

`foreman/migrations.py`, `foreman/store.py`, `foreman/meta_agent.py`,
`foreman/dashboard_backend.py`, `foreman/cli.py`, `tests/test_meta_agent.py`
(new), `tests/test_migrations.py`, `tests/test_cli.py`, `tests/test_dashboard.py`.

## Test results

- `tests.test_meta_agent` (7 new), `tests.test_migrations`, targeted CLI +
  dashboard tests
- Full suite: 528 tests passed
- `scripts/validate_repo_memory.py`; `git diff --check`

## Follow-ups

- Stacked-on by Sprint 50 (executor overrides / escalation ladder).
