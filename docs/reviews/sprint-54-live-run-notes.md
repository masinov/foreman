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

## Run 2 — slice 2a, engine command table (task `task-add-the-engine-command-table-and-foreman-engine-cli`), first resident run

Started 12:32:51 UTC with `foreman serve foreman` (the code merged by run 1).
The engine lock was acquired and heartbeated on its own connection (lease
renewed every 20 s, 120 s duration), the pass picked task 2 within a second
because its dependency on task 1 was satisfied, and the JSON log narrated the
step at INFO with the agent firehose at DEBUG.

| # | Sev | Observation | Consequence |
|---|-----|-------------|-------------|
| 25 | minor | The per-task lease of task 1 (holder: the first `foreman run`) is still `active` in `leases` after the task is done and its process is long gone; its expiry passed at 12:12 but rows expire lazily. | Lease inspection lies until someone calls `expire_leases`; release task leases at `mark_done` and when a run process exits at a gate, or expire on read. |
| 26 | blocker | 56 seconds into the develop step the Claude subscription's five-hour window ran out. The CLI streamed `rate_limit_event` with `status: rejected` and `resetsAt`, then a `result` with `is_error` and the text "You've hit your session limit · resets 3:20pm". The runner surfaced it as a plain `agent.error`, the step outcome became `error`, the workflow had no transition for it, and the task was **blocked** with the quota message as its `blocked_reason`, `failure_type` left null. The resident engine then idled with nothing runnable. | Quota exhaustion is an infrastructure condition with a known reset time, not a task defect. Unattended operation needs: classify it, keep the task resumable at its step, record `failure_type=quota`, and have the resident engine wait until the reset before the next pass. Fixed in sprint 54 (`fix/runner-quota-exhaustion`). |
| 27 | major | With one blocked task and nothing runnable, `foreman serve` ran a full pass every poll interval (5 s) and logged `serve.pass_completed` plus `serve.idle` at INFO each time: about 1,400 log lines per idle hour, and `run_project` (settings, workflow load, task selection) executed every 5 s. | The poll interval is a fallback for missed wake-ups, not a schedule. Log the idle transition once and repeat passes at DEBUG; on a poll wake without a `data_version` change skip the pass entirely. Fixed alongside 26. |
| 28 | minor | Lease inspection: after the engine stopped, its engine lease is `released` correctly (SIGTERM path verified live: `serve.stopping`, `serve.stopped`, exit 0, lock released). | Positive result; recorded for completeness. |

**Resolution.** The serve process was stopped with SIGTERM (clean: `serve.stopping`,
`serve.stopped`, exit 0, lock released) after 3,517 idle passes. Branch
`fix/runner-quota-exhaustion` teaches the runner to raise `QuotaExhaustedError`
(from a rejected `rate_limit_event` or the limit text) with the reset time,
`run_with_retry` to surface it once without retries, the orchestrator to pause
the task at its step with `failure_type=quota` and `engine.quota_exhausted`
(no loop budget spent, lease released, checkout restored), `foreman run` to
exit 75 with the reset time, and `foreman serve` to wait for the reset (bounded
between one minute and six hours) before the next pass. Idle passes are now
narrated once at INFO and repeated at DEBUG. Task 2 was unblocked and the
resident run resumed after the merge.

## Run 3 — slice 2a again, resident run with the quota fix

`foreman serve foreman` started 17:35:40 UTC on the merged fix, found nothing runnable
(task 2 still blocked), and idled with one INFO line. `foreman task unblock` from
another process committed at 17:35:41; the engine woke on `data_version` within a
second, selected task 2, and resumed the developer's earlier session (`--resume`),
so the reading it had done before the quota hit was not repeated.

**Slice 2a result.** Develop 25.1 min on the resumed session ($13.11), tests, review approve (5.3 min, $0.76), gate. Eight conventional commits: migration 15 with CHECK constraints, `EngineCommand` and a token-free `EngineLockView`, five store methods, a `command_poll` seam called before every step and on every silent tick, `pause`/`resume`/`run_task`/`stop_task`/`shutdown` semantics with stale-command rejection at startup, `foreman engine` CLI, ADR-0011 amendment, 45 tests (725 total in the agent's run). The agent found and fixed two of its own bugs through its tests (an exception-ordering shadowing and a `run_task` request being overwritten). With the idle-logging fix the resident log held 182 lines after thirty idle minutes instead of 1,400 per hour.

| # | Sev | Observation | Consequence |
|---|-----|-------------|-------------|
| 29 | major | A task branch is created on the task's first develop visit and never refreshed: task 2's branch dates from the quota-failed attempt at 12:32, so by the time it reached the gate `main` had taken the quota fix, which touches the same files. The merge step will conflict and cost a full develop → test → review cycle. | Sync the task branch with the default branch at the start of every develop visit when the merge is clean (`sync_branch_with_base` already exists; today it runs only after a merge conflict). Queued as a sprint fix. |
| 30 | minor | `foreman approve` and `foreman deny` still run the rest of the workflow inline in the CLI process while a resident engine may be up; the engine was stopped by hand before approving to avoid a lease race. | Slice 2b should turn a gate decision into a command the resident engine applies (`resume_gate`), with the CLI returning immediately when an engine is resident. |

**Merge round and the second quota hit.** Approving task 2 ran the merge inline: it
conflicted on `foreman/orchestrator.py`, `foreman/serve.py`, `foreman/cli.py`,
`CHANGELOG.md`, and more, because the branch predates the quota fix on `main`. The
conflict-resolution pass ran 10.8 minutes on the resumed session ($5.36), reported
"All three pass now. Let me run the full suite and finish the merge", and was then cut
off by the five-hour window again (resets 18:40 UTC). The new quota handling did its
job: the task stayed `in_progress` at `develop` with `failure_type=quota` and an
`engine.quota_exhausted` event, no loop budget spent, nothing blocked.

| # | Sev | Observation | Consequence |
|---|-----|-------------|-------------|
| 31 | major | The pass was interrupted with a merge in progress: `MERGE_HEAD` present, two files still conflicted, the rest resolved and staged. The next develop visit's conflict-recovery path would run `git merge main` again, fail with "not concluded", and `git merge --abort`, throwing the developer's resolution away. | Fixed with F3: a develop visit that finds an unconcluded merge leaves it alone and tells the developer to finish it (`engine.branch_sync` with mode `merge_in_progress`). |
| 32 | minor | `foreman approve` printed "Failed to approve task: … paused until the backend quota resets" and exited 1, although the decision was recorded and the merge attempted; only the follow-on develop pass paused. | Fixed with F3: approve and deny report the pause honestly and exit 75. |
| 33 | major (structural) | With the working tree mid-merge on the task branch, `./venv/bin/foreman` in that checkout cannot even import (conflict markers in `orchestrator.py`): the engine's code and the code it edits are the same files. The resident engine had to be started from a separate clone pointed at the dogfood database. | The strongest argument yet for slice 6 (worktree per task): the engine must run from an installed package or a stable checkout, never from the tree the agent edits. |
| 34 | minor | The orchestrator asserts after every step that the default branch did not move, and blocks the task if it did. With one local engine that is a safety net; with pull requests and a remote `main` it is a single-machine assumption. | Revisit when integration moves to pull requests (sprint 55). |

**Resolution.** Branch `fix/task-branch-refresh` (F3): every develop visit first merges
the default branch into the task branch when it is behind and the merge is clean
(`engine.branch_sync`, mode `refresh`), hands a conflicting refresh to the developer as
guidance (mode `refresh_conflict`), never aborts a merge the developer was concluding
(mode `merge_in_progress`), and `foreman approve`/`deny` exit 75 with an honest message
when the follow-on step pauses on quota. The two merge-conflict tests were rewritten
around the real scenario: `main` moving while the task waits at a human gate.

## Run 5 — slice 2b (dashboard onto the resident engine), resident run from the repository

Task 2 concluded its merge on the resumed session in 4 minutes ($6.53) once the
`merge_in_progress` guard and the no-op checkout let the pass reach the tree as it was
left; test, review, gate, approve, and the engine's merge followed (`fd28d94`). The
resident engine then picked task 3 within seconds of the merge commit.

| # | Sev | Observation | Consequence |
|---|-----|-------------|-------------|
| 35 | major (operator + product) | A second resident engine survived a mis-targeted stop (`pgrep -f` matched the shell wrapper, not the engine), so while I merged the F3 branch on `main` in the shared checkout, that engine had already started task 3's develop step in the same checkout. The tree was switched under a running agent, and `main` moved during its step, which the post-step invariant would have blocked. Recovered by hand: checkout returned to the task branch before the agent wrote anything, local `main` parked at the commit the step captured until the gate. | Two product gaps behind one mistake: the engine lease names a UUID, not a process (`foreman engine status` cannot say which pid to stop), and the engine still works in the operator's checkout. Record the pid and host on the lease; slice 6 (worktree per task) removes the shared tree. |
| 36 | minor | `foreman serve` refused to start with a clear `serve.lock_busy` line naming the holder and the expiry, exactly as designed; the operator surface did its job, the operator did not read it first. | Positive; recorded for completeness. |
| 37 | major | `_dependencies_satisfied` counts a **cancelled** dependency as satisfied. Cancelling the queued intake task made the queued policy task runnable, and the still-resident engine started a developer on it (in a checkout that was mid-merge) before the cancel of the policy task itself was applied; the cancel then lost to the engine's `in_progress` write. Stopped by SIGTERM after about a minute. | A cancelled prerequisite is a decision, not a delivery: the dependent task should be blocked with "dependency cancelled" for a person to re-plan, never auto-started. Fix queued as F4. Also: `task cancel` must refuse (or stop) a task with a running run instead of being overwritten. |

**Slice 2b result.** Develop 23.6 min ($15.54), test, review **steer** (a stale
"next slice" paragraph in `docs/ARCHITECTURE.md`), corrective develop 2.4 min ($2.45)
on the resumed session, test, review approve, gate. The first live STEER round: the
reviewer's single corrective line was enough for the developer to fix and re-verify.
Because the branch predates F3 on `main`, the maintainer merged `main` into the branch
by hand before approving (the agent had fixed the `task unblock` bug independently,
through its shared `blocked_kind` derivation, so that side was kept); the engine's
merge then landed clean at `3ff6936`.

**Resolution.** Branch `fix/cancelled-dependency-blocks` (F4): only a `done`
dependency satisfies; a task whose dependency was cancelled is blocked with
"Dependency cancelled: …" and an `engine.attention_needed` trigger
`dependency_cancelled`, once; `foreman task cancel` and the dashboard cancel refuse a
task with a running run while an engine is resident and point at
`foreman engine stop-task`.
