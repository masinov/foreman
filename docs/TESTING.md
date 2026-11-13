# TESTING

## Principle

Foreman testing should verify durable workflow behavior, not just syntax.
Compilation-only checks are insufficient.
String-presence assertions are acceptable for bootstrap seams, but not as the
final validation strategy for finished product surfaces.

## Current baseline

The repo is still pre-release, so the current mandatory checks include both
repo-memory validation and code-level regression coverage:

- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/repo_validation.py`
- `./venv/bin/python -m py_compile scripts/validate_repo_memory.py`
- `./venv/bin/pip install -e . --no-build-isolation`
- `npm --prefix frontend run lint`
- `npm --prefix frontend test`
- `npm --prefix frontend run build`
- `./venv/bin/python scripts/dashboard_dev.py --help`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/ruff check foreman tests scripts` (install with
  `./venv/bin/pip install -e ".[dev]"`)

CI (`.github/workflows/ci.yml`) runs the suite, ruff, the repo-memory
validation, and the frontend tests and build. The built bundle under
`foreman/dashboard_frontend_dist` is not in git: the Python job builds it
before the tests, and the tests that serve it skip when it is absent.

## Running the suite inside a task worktree

Foreman runs every task in its own git worktree (ADR-0012), and the engine runs
this repository's own `test_command` in that tree. Two things follow, and both
are load-bearing:

**1. The CLI suite must not repoint the operator's virtualenv.**
`tests/test_cli.py` used to run `pip install -e .` in `setUpClass` so the
`venv/bin/foreman` console script matched the checkout under test. Inside a
worktree that is actively harmful: the worktree borrows the operator's `venv/`
through a symlink, so the reinstall would repoint the operator's own `foreman`
command at a temporary tree that `mark_done` later deletes.

The suite now:

- probes which `foreman` package the interpreter imports on its own (no
  `PYTHONPATH`, run outside the repository), and **skips the reinstall**
  whenever that is a different checkout — recording the reason on
  `ForemanCLISmokeTests.reinstall_skipped_for`;
- runs every CLI subprocess as `python -m foreman` with `PYTHONPATH` pinned to
  the checkout the test file lives in, so the code under test is always this
  checkout regardless of what the virtualenv is wired to;
- uses `sys.executable` rather than a hard-coded `venv/bin/python`, because a
  worktree need not have a `venv/` at all.

The reinstall still happens in the normal case — running the suite from the
operator's own checkout — so the console entry point stays fresh there.

**2. The test command needs the local tooling.** A worktree is a clean
checkout, so `./venv/bin/python` does not exist in it until the project's
`worktree_link_paths` setting names `venv`. For this repository:

```bash
./venv/bin/foreman config foreman --set 'worktree_link_paths=["venv"]'
```

Verify both properties after changing either:

```bash
git worktree add --force /tmp/wt-selftest HEAD --detach
ln -s "$PWD/venv" /tmp/wt-selftest/venv
(cd /tmp/wt-selftest && ./venv/bin/python -m unittest discover -s tests)
# then confirm the operator venv still points at the operator checkout:
./venv/bin/python -c "import foreman, pathlib; print(pathlib.Path(foreman.__file__).parent)"
git worktree remove --force /tmp/wt-selftest
```

## Slice coverage that exists today

The current suite covers:

- `tests/test_store.py` for SQLite round-trips, status-filtered reads, run
  totals, recent-event slices, incremental event cursors, sprint-scoped event
  queries, and event retention pruning
- `tests/test_store_safety.py` for WAL and busy handling, hot-write retries
  under a foreign lock, sequence-based task keys under concurrent writers,
  dependent-aware deletes and pruning, atomic migrations, the v13 to v14
  upgrade on a legacy database, and settings validation at the orchestrator,
  dashboard, and CLI boundaries
- `tests/test_runner_lifecycle.py` for the managed-process layer with real
  subprocesses (silent ticks, stderr floods, process-group kills, the SIGTERM
  handler), silent-agent time gates in both runners, the Codex startup
  timeout, the test built-in timeout, and orchestrator tick, shutdown, and
  lease-loss handling
- `tests/test_output_contract.py` for the decision grammar (prefixes,
  placeholders, ambiguity, undeclared verdicts), fence-aware and multi-line
  signal parsing, Claude result-signal deduplication, role-declared outcomes,
  review kinds and signal allowlists, the final-message marker rule, and a
  custom TOML reviewer plus tiered review flowing through the merge guard
- `tests/test_workflow_gates.py` for the shipped workflow shapes (test before
  review, a policy-governed `merge_approval` gate), gate policy settings and
  per-task overrides, auto-approval with a decision record, a human gate that
  pauses and resumes to merge, and test failures returning to develop before
  any review
- `tests/test_dashboard_safety.py` for token authentication on `/api`
  (header, alternate header, query), open shell and assets, CORS off by
  default and allowlisted origins, manager routes forbidden when disabled,
  the bounded events page, the bind security policy and its CLI flags, and
  repository path validation on project creation
- `tests/test_roles.py` and `tests/test_workflows.py` for shipped declarative
  configuration loading and validation
- `tests/test_runner_env.py` for role `[agent.env]` value resolution and
  missing-secret preflight classification
- `tests/test_worktrees.py` for the per-task git worktrees: layout and the
  `worktree_root` override, create/reuse/remove/prune, the refusal paths
  (no branch, a path outside the worktree root, a root git would commit, a
  git without worktree support), migration 16, and the engine guarantees —
  the operator's checkout never moves during a task, agent steps and the test
  command run in the task's tree, the merge lands through the integration
  worktree, gate and quota pauses keep the tree, and `mark_done` removes it
- `tests/test_scaffold.py` for generated `AGENTS.md`, idempotent `.gitignore`
  updates, default `.foreman.db` ignore behavior, and repo re-initialization
  behavior
- `tests/test_context.py` for `.foreman/context.md` and `.foreman/status.md`
  rendering
- the engine tests, split by what they cover, all on the fixtures in
  `tests/engine_support.py` (`RepoTestCase`, `OrchestratorTestCase`, scripted
  executors and runners):
  `test_engine_workflow.py` (a task through the shipped workflows),
  `test_engine_branches.py` (refresh, conflicts, the default branch),
  `test_engine_gates.py`, `test_engine_agent_step.py` (backends, sessions,
  retries, heartbeats), `test_engine_recovery.py` (leases, stale runs,
  crashes), `test_engine_task_control.py` (operator changes, limits,
  dependencies), `test_engine_signals.py`, `test_engine_selection.py`,
  `test_engine_model_selection.py`, `test_engine_evidence.py`,
  `test_engine_completion_guard.py`, `test_engine_prompts.py`,
  `test_engine_sprints.py`
- `tests/test_git.py` for the git helpers against real repositories
- `tests/test_store_concurrency.py` for several connections writing at once
  (lease races, event writes, task keys, cancel against engine writes)
- `tests/test_cli.py` for CLI smoke paths, repo-local DB discovery, explicit
  override semantics, secure workflow initialization, live watch tails,
  monitoring command subprocess behavior, and the shipped project, sprint,
  task, run, and config command flows
- `tests/test_runner_claude.py` for Claude Code command construction, startup
  preflight, optional env passing, event mapping, signal extraction, and
  failure handling
- `tests/test_runner_codex.py` for Codex app-server startup, thread start or
  resume, startup preflight, optional env passing, approval responses, streamed
  event mapping, and failure handling
- `tests/test_dashboard.py` for the extracted dashboard service contract,
  FastAPI HTTP routes, built frontend shell delivery, frontend-dev redirect
  behavior, task detail data, human message persistence, incremental
  sprint-event stream payloads, and approve or deny integration behavior
- `frontend/src/api/` tests for the `/api/v1` client and its error envelope,
  `useResource` (stale responses ignored, errors as sentences, reload, the
  200 ms placeholder delay), and the workspace loader against fake API
  answers
- `frontend/src/app/` tests for the route table (every ADR-0020 route,
  not-found, and the terminal commands a route without a page names) and the
  shell: route-driven breadcrumb, the not-built page naming those commands
  and linking nowhere, `/dashboard/legacy` rendering not-found, anchors,
  in-app navigation and back
- `frontend/src/ui/` one test file per primitive
- `frontend/src/pages/workspace/WorkspacePage.test.jsx` for rows from API
  data, the empty Needs you, Approve calling the approve endpoint and
  reloading, an API error shown, placeholders after 200 ms, and the cap of 5
- `frontend/src/styles/rules.test.js` for the design rules: no colour or size
  outside `tokens.css`, no inline styles, no `fetch` in pages or primitives

## Checking the look

Tests run in jsdom and cannot see a page. `scripts/dashboard_shot.mjs` can:
it drives the installed Chrome headless and writes a PNG, after clicking,
hovering or typing if asked.

```bash
node scripts/dashboard_shot.mjs http://localhost:8080/dashboard/projects/foreman /tmp/project.png
node scripts/dashboard_shot.mjs http://localhost:8080/dashboard /tmp/add.png "click:Add project"
node scripts/dashboard_shot.mjs http://localhost:8080/dashboard/projects/foreman /tmp/phone.png --size=390x844
node scripts/dashboard_shot.mjs http://localhost:8080/dashboard /tmp/zoom.png --scale=3 --size=700x300
```

What a change to the frontend is checked against, before a person sees it:

1. Tabs change what a page shows. Anything that opens another page is a
   button or a link and is never in a tab row.
2. Every breadcrumb step is a place: clicking it lands on a page that shows
   that breadcrumb. No tab names. The wordmark is the only link to the
   workspace.
3. One way to each place; no two adjacent controls go to the same page.
4. A section title sits on a rule, joined to what it names. It is a short
   name; details and actions go beside it on the same row.
5. A count is a figure beside its label: smaller, a fixed gap away, on the
   baseline. Gold only when it counts things that wait for a person.
6. Gold means "needs you"; green, red and blue mean a result or a state.
7. The same thing is said the same way on every page (checks, task counts,
   engine state).
8. Text on one line shares a baseline (check at `--scale=3`); numbers sit
   under their header.
9. A highlight stays inside its container and content does not touch its
   edge; rows of one list are one height.
10. Nothing wraps that would fit; keys and short facts never break.
11. Never show an id, a placeholder or a filler line.
12. Long lists say N of M and offer the rest; a pick shows its result beside
    the list.
13. Empty states keep their container, with a sentence inside.
14. Icons accompany words.
15. Hints say plainly what to type.

Take the shot at 1440 wide and at 390 wide. Open every dialog and menu the
change touches. Use a copy of the database when a step would change state.

## Expected testing layers

Unit tests:

- model validation
- SQLite store round-trips
- role and workflow parsing
- signal parsing
- dashboard service payloads and action behavior
- dashboard FastAPI route behavior over ASGI transport
- dashboard shell and asset delivery over the dedicated frontend boundary
- dashboard frontend-dev redirect behavior and local proxy assumptions
- dashboard live transport serialization
- git helper behavior that can be isolated
- frontend component behavior in the dedicated React app

Integration tests:

- per-task worktree lifecycle across a full workflow run
- project initialization
- sprint and task lifecycle
- orchestrator transitions
- `development_secure` approval and denial paths through `security_review`
- event-retention pruning with preserved blocked and in-progress task history
- CLI live-tail watch behavior across project, sprint, and run scopes
- built-in test, merge, and human-gate steps
- context projection into `.foreman/`
- cross-invocation native session reuse for Claude Code, Codex, and
  non-persistent reviewer roles
- dashboard API contract behavior independent of the frontend implementation
- local dashboard dev-runner smoke behavior where practical

Runner smoke tests:

- Claude Code runner wiring
- Codex runner wiring
- preflight classification plus event capture and retry behavior

UI validation:

- manual checks against `docs/design/dashboard-v7/`
- project dashboard navigation
- sprint board interactions
- activity feed behavior and live stream updates
- alignment between dashboard sprint streaming and CLI watch tailing
- human message, filter, and approve or deny flows
- browser-driven validation for the dedicated frontend

## Definition of done

Do not mark a task done unless:

- the relevant automated checks pass,
- new behavior is covered by tests when practical,
- user-visible changes include validation notes,
- the docs reflect the new reality.

For product UI work, "done" should include API contract coverage, frontend
behavior coverage, and browser or bundle-level validation rather than only
backend tests that inspect HTML strings.

If a slice cannot reasonably add tests yet, explain why in the PR summary and
record the follow-up explicitly.
