# Sprint 54 live-run notes

Foreman driving Foreman. Each slice of sprint 54 that the engine can carry
is planned as a dogfood task in the repository's own `.foreman.db` and run
with the engine (`foreman run foreman`, and from slice 2 on `foreman serve
foreman`). This file records what the engine did, what a person had to do,
and every deficiency observed, with a severity:

- **blocker** — the pipeline cannot complete the task without a person or a
  code change; fixed inside the sprint.
- **major** — the task completes but the outcome or the audit trail is
  wrong or misleading; queued as a sprint slice or backlog item.
- **minor** — friction; recorded for the backlog.

## Setup (2026-09-04)

- Dogfood project `foreman`, workflow `development`,
  `task_selection_mode=directed`.
- Settings changed for the live run: `merge_approval=human` (a person
  inspects the branch before the engine merges),
  `default_model=claude-opus-5` for the developer role (the shipped
  `code_reviewer` role pins `claude-sonnet-4-6`), `cost_limit_per_task_usd=75`
  as a ceiling.
- The previous dogfood sprint (`Review Phase 0 correctness`) was stale: its
  one task had been done by hand months ago. Cancelled and completed by hand.
- Slice 1 (`foreman serve`) was planned by hand as a full task description
  plus acceptance criteria (see the task record); the engine has no planner
  step yet (sprint 54 slice 5).

## Run 1 summary — slice 1, `foreman serve` (task `task-add-foreman-serve-resident-engine-worker-with-a-project-engine-lock`)

Merged to `main` at `a462659` by the engine's own merge step after three
gate rounds. Wall clock 11:41 to 12:30 UTC (49 minutes), 18 runs, 1,725
events, $21.96, 140k billed tokens.

| Round | Steps | Agent cost | What happened |
|---|---|---|---|
| 1 | develop 24.5 min → test → review (approve, 1.3 min) → gate | $10.30 | Full slice on four conventional commits, ADR-0011, PR note, docs; 645 tests green in the agent's own run. |
| 2 | gate `deny` with two corrections → develop 6.1 min (resumed session) → test → review (approve) → gate | $4.87 | Log-level mapping by event family and a `serve.lock_busy` log line, one commit. |
| 3 | gate `approve` → merge **conflict** (`docs/STATUS.md`, `CHANGELOG.md`) → develop 5.6 min → test → review (approve) → gate → `approve` → merge → done | $6.79 | `main` had taken the live-run runner fix meanwhile; the agent merged `main` into the branch and resolved both files. |

What a person did: wrote the task spec, read the diff, denied once with a
note, approved twice, and rebuilt the virtualenv after an operator mistake
(see the incident below). Everything else was the engine.

## Observations

### Run 1 — slice 1 (`foreman serve`), developer step

Started 2026-09-04T11:41Z, model `claude-opus-5` (project default), branch
`feat/task-add-foreman-serve-resident-engine-worker-with-a-project-engine-lock`.

| # | Sev | Observation | Consequence |
|---|-----|-------------|-------------|
| 1 | major | The developer prompt carries the task description and acceptance criteria twice: once from `{task_description}` / `{acceptance_criteria}` and again inside `{sprint_context}` (the "Current Task" section of `.foreman/context.md`). 28 KB prompt, about 9 KB duplicated. | Token waste on every develop visit; the context file is meant for files-on-disk reading, not prompt inlining. Either drop the current-task block from the prompt copy or stop inlining `context.md`. |
| 2 | minor | Branch names are generated from the task id, which already embeds the title: `feat/task-add-foreman-serve-resident-engine-worker-with-a-project-engine-lock` (76 chars). Task keys exist (`FM-n`) and are unused here. | Unreadable branches and PR titles. Use `<type>/<task-key>-<short-slug>`. |
| 3 | minor | `foreman task show` renders `agent.tool_use` and `agent.raw_output` as "(no payload details)"; only `agent.command` shows the command. | The CLI cannot tell what the agent is reading or editing; the dashboard has the same payloads. Summarize tool name + primary argument. |
| 4 | minor | `foreman watch --idle-timeout` never fires while an agent is streaming, so a bounded tail is impossible; there is no `--max-events` or duration cap. | Scripts cannot sample the stream. |
| 5 | minor | `write_pr_summaries` and `write_checkpoint_notes` are scaffold defaults with no reader anywhere in the engine. | Dead settings shown in `foreman config`. Remove or implement. |
| 6 | minor | The context projection's "Completed Sprint Summaries" reports `Tasks completed: 0/1`, `Key deliverables: (none recorded)` for the stale sprint, because completion is by-hand. | Noise; harmless. |
| 7 | major | The engine checks out the task branch in the operator's checkout. Anyone working in the repository while the engine runs (including this session) must stay off git and off the tree. | Confirms the worktree-per-task slice (sprint 54 slice 6) as a prerequisite for anything but a dedicated machine. |
| 8 | minor | The run row shows `tokens=0 cost=$0.00` until the result event; the lease expiry shown to the agent in `context.md` (5 minutes) is an implementation detail the agent cannot use. | Cosmetic. |
| 9 | major | The current Claude Code CLI streams `{"type":"system","subtype":"thinking_tokens",...}` progress lines while the model thinks. `ClaudeCodeRunner` maps every unrecognized line to a persisted `agent.tool_use` with tool `claude.stream_event`, and the raw line is persisted again as `agent.raw_output`. Two minutes of thinking produced 95 fake tool-use events and 139 raw lines (550 KB). | Event-table bloat at roughly two rows per second, a misleading tool-use count in the dashboard, and noise in the stream. Map progress subtypes to a non-persisted tick; persist raw output only for lines that carry content. Fixed in sprint 54 (`fix/runner-progress-lines`). |
| 10 | minor | The developer agent patched files with `python - <<'PY'` (system Python) despite the AGENTS.md rule to use `./venv/bin/python` only. Harmless for text edits, but the rule is not enforced by anything. | The role prompt restates the rule; enforcement would need a tool allowlist or a repository hook. Record only. |
| 11 | major | `tests/test_cli.py` reinstalls the package into the shared `./venv` (`pip install -e .`) from whatever checkout runs it. Running the suite from a second checkout (a worktree per task, a clone) repoints the venv at that checkout. | Blocks slice 6 (worktree per task) unless the test harness stops mutating the venv; the live-run fix branch had to skip that test file. |

**Developer step result.** 24.5 minutes, $9.64, 95k tokens, four conventional commits, 645 tests green in the agent's own run, working tree clean. The agent stated its plan first (AGENTS.md planning rule), wrote ADR-0011, a PR note, and updated `docs/STATUS.md` and `docs/sprints/current.md` itself. Quality on read-through: the lock, loop, and logging modules are production-shaped; the orchestrator gained three small seams (`maintenance=`, `TaskExecutionError`, `block_task_for_error`) rather than a rewrite.

| # | Sev | Observation | Consequence |
|---|-----|-------------|-------------|
| 12 | minor | The `_builtin:run_tests` outcome detail starts with stdout noise from a test that prints (`Updated task executor overrides ...`), because the built-in stores the tail of combined output. | The detail is what reviewers and the evidence see; a summary line (`Ran N tests ... OK`) plus the failure block would serve better than a raw tail. |
| 13 | minor | The agent marked slice 1 `done` in `docs/sprints/current.md` before review and merge. | Sprint memory written by the implementer is optimistic by construction; the engine should own status projection (the spec's SQLite-to-markdown direction). |
| 14 | major (design) | The mirror of persisted events into the process log is at INFO for every family, including `agent.raw_output`, `agent.prompt`, and tool payloads. A resident engine will log several lines per second of agent output. | Sent back through the merge gate as a `deny` note to exercise the corrective loop; high-volume families belong at DEBUG. |
| 15 | major | The heuristic completion evidence scored the finished slice 67.9/100 ("weak", "1/9 criteria addressed + 3 partial") although every criterion is met and 645 tests pass. The criteria are prose with backticked identifiers; the keyword-overlap heuristic cannot see that `tests/test_serve.py` proves "picks up a task added from another process". The reviewer prompt tells the model to weigh this heavily. | A false "weak" verdict biases every review and can block the merge through the proof gate, forcing a waiver for correct work. Confirms the Phase 1 item "facts-based verification": drop the score, judge on by default, criteria as checkable facts. |

**Test and review steps.** `_builtin:run_tests` passed (645 tests). `code_reviewer` (Sonnet 4.6, read-only tools) answered `APPROVE` in 80 s for $0.66 despite the "weak" evidence, so the prompt's "weigh the evidence heavily" instruction did not produce a false deny here. The task then paused at `merge_approval` ("Awaiting human approval"); the engine exited 0 with stop reason `blocked` and restored the checkout to `main`.

| # | Sev | Observation | Consequence |
|---|-----|-------------|-------------|
| 16 | minor (corrected) | The evidence cached on the task at review time shows `proof_status=failed` (8 of 9 criteria "not fully addressed"). At merge time the built-in rebuilds the evidence, and `build_completion_evidence` lets an explicit review approval override the heuristic's criteria verdict, so the proof gate passed without a waiver on the second round. The first-round cache is what reviewers and the dashboard see, though. | The heuristic's verdict is shown as if it were a finding while the gate itself already trusts the reviewer over it; the two should agree. Finding 15 stands. |
| 17 | minor | The reviewer's transcript is a single `APPROVE` line; the reviewer prompt asks for exactly one line, so there is no record of what was checked. | Keep the one-line decision for the parser but ask for a short findings block above it; the parser already reads the final message only. |
| 18 | minor | The engine's own process printed nothing to stderr during a 27-minute run; progress is only visible through the database. | Slice 1 adds JSON logs for `serve`; `run` should default to a terse progress line per step. |

**Incident during the run (operator error, recorded because the product must prevent it).** The live-run fix was built in a scratch clone whose `venv` was a symlink to the repository's virtualenv. `.gitignore` says `venv/`, which matches a directory but not a symlink, so `git add -A` committed the link. Fast-forwarding that commit onto `main` made git replace the real `venv` directory with a link to itself and delete the ignored contents; the environment was rebuilt from `pyproject.toml` (Python 3.12.7) and the commit amended before anything was pushed.

| # | Sev | Observation | Consequence |
|---|-----|-------------|-------------|
| 19 | major | Anything merged into the default branch lands directly in the operator's checkout and can destroy untracked state there; there is no pull request, no CI, and no isolation between "what the engine merged" and "where people work". | The strongest live argument for slice 6 (worktree per task under a Foreman-owned directory) and sprint 55 (integration through pull requests). Also: the merge preflight should refuse a source branch that adds a symlink or a path matching an ignore rule. |
| 20 | minor | `.gitignore` uses `venv/`; a bare `venv` pattern would also cover a symlink. | Change the ignore rule. |

**Corrective loop (gate deny → develop).** `foreman deny --note` resumed the workflow inline in the CLI process: a `_builtin:human_gate` run recorded the decision and the note, the developer step started 30 ms later with `--resume <session>` (session persistence survived the pause and the process boundary), and the agent began the two corrections within 15 seconds with no re-reading of the codebase.

| # | Sev | Observation | Consequence |
|---|-----|-------------|-------------|
| 21 | minor | `foreman approve` / `foreman deny` run the rest of the workflow inline in the CLI process, without the engine lock or shutdown handlers, for as long as the agent takes. | With `foreman serve` resident this must become a command (`resume` with the decision) the engine consumes; the CLI should return immediately. Folded into task 2's `engine_commands` design as a follow-up. |
| 22 | minor | While a run is `running`, its row has `session_id=NULL` even when it was launched with `--resume`; the id is filled from `agent.completed`. | Operators cannot see which session a live run continues; store the resumed id at launch. |

**Merge round.** `foreman approve` ran the merge inline: preflight passed, the proof gate passed (review approval overrides the heuristic), and `git merge --no-ff` conflicted on `docs/STATUS.md` and `CHANGELOG.md` because `main` had taken the runner fix in the meantime. The engine emitted `engine.merge_conflict`, transitioned `merge → develop` with the conflict text as carried output, and started a conflict-resolution developer pass on the resumed session.

| # | Sev | Observation | Consequence |
|---|-----|-------------|-------------|
| 23 | major (structural) | Both the engine's agent and people append "Latest update" sections at the top of `docs/STATUS.md` and `CHANGELOG.md`, so any two branches that overlap in time conflict there by construction, and each conflict costs a developer pass plus another test and review cycle. | Repo-memory markdown is a conflict magnet. The spec's direction (SQLite as truth, markdown as projection written by the engine at merge time) removes the cause; until then, per-branch notes (`docs/prs/<branch>.md`) should carry the update and the shared files should be regenerated, not hand-edited, by agents. |
| 24 | minor | The conflict-resolution pass is a full `develop → test → review → merge_approval` cycle even when only two markdown files conflict. | A "rebase-only" resolution step (built-in sync, then straight to merge when the diff against the previously reviewed head is docs-only) would save a review per conflict. |
