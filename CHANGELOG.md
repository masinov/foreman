# Changelog

All notable changes to this repository should be documented here.

The repo is still pre-release, so entries currently track milestone and repo
memory changes rather than versioned product releases.

## [Unreleased]

### Sprint 62

- The engine runs one task at a time (ADR-0039, owner 2026-11-24). A task waiting for a user's decision at a gate holds the queue: nothing else starts until it is decided, and then it is merged before the next task starts from the default branch it left. The side door that merged approved tasks inside another task's step is removed (ADR-0011's 2026-11-15 amendment withdrawn). A task blocked by a failure does not hold the queue.
- A reviewer is shown the evidence as it is now. It reused a copy saved on the task until the branch head moved, so a test run made again on the same commit went unseen and FOR-52 was sent back for checks that had passed.
- A review step reads as approved, not committed, in a task's Steps table when the merge step had brought the branch up to date; the finished sprints' Spend title sits with its figures.

- A merge refused for lack of proof says why in plain words, and what to do (sprint 62 slice 9, run through Foreman). `proof_refusal_text` (`foreman/engine/builtins/completion.py`) writes the blocked reason as sentences: a short heading chosen by precedence (the branch changed after it was tested and reviewed; the tests failed; no code review approved the latest change; the tests have not run), the facts said once ("Tests and review ran on 7d8423b; the branch is now at 8fa6655."), and the step a person can take ("Unblock it to test and review it again.", "Send it back to fix the tests."). No "proof_status", "Current:" or "Completion proof". Commit ids in the evidence's reasons are 7 characters. The structured evidence is unchanged. The task page's decision box shows the first sentence as its heading and the rest beneath it.

- After a decision, and while a task waits, the page says what happens next (sprint 62 slice 8, run through Foreman). A task the running engine is not on reads "Waiting · Develop" (hover: "The engine runs it after FOR-53"), its Steps row "Waiting here"; "Stopped" only where no engine runs. A pending Run next is `run_next: true` on the task and the sprint's task list (`ForemanStore.run_requested_task_ids`); the page shows a disabled "Runs next" button, "Runs next · Develop" and a "Runs next" step row, and the engine completes the `run_task` command when it starts the task instead of when the pass ends. A step a task was sent back to says why on its Steps row ("sent back: merge conflict", "sent back by review", "tests failed"). A gate's Attempts counts its pause and its decision as one. An approval or a send-back is one sentence built in `pages/shared/decisionWords.js` and by `decision_sentence` for the server's `message` ("Approved FOR-51. Foreman goes on with Merge.", "...It waits at Merge until the engine is started.", "Sent FOR-51 back to Develop."), without backticks and with "started" for the engine. Every success sentence after an action is now a shared toast (`ui/Toast`: `ToastProvider`, `useToast`, `useNotice`) in the window's bottom left corner for about 6 seconds; errors stay inline.

- `foreman task edit` changes every field a person can edit, and commands take a task's key (sprint 62 slice 7, run through Foreman). New `--type`, `--description`, `--criteria`, `--description-file` and `--criteria-file` (`-` reads standard input) and `--edit description|criteria` (opens `$VISUAL`, else `$EDITOR`, else `nano`/`vi`, only on a terminal; unchanged or emptied changes nothing), all through `Mutations.edit_task` with `via="cli"`; contradictory options are refused and the output names each changed field without printing the text. Every command that takes a task (`task show/edit/block/...`, `history`, `backlog`, `engine`, gates) accepts its key (`FOR-56`) as well as its id through `resolve_task_or_print`, backed by `ForemanStore.find_tasks_by_key`; a key in several projects is refused, naming them. The manager's operating contract names the options and keys.

- The project page's controls sit on its tab row, and its headings name groups (sprint 62 slice 5, run through Foreman). New sprint (Sprints) and the All | Sprints | Engine filter (Activity) are on the tab line at the right, built with the same `tabLine(controls)` as the sprint page, and wrap under the tabs on a phone. Sprints keeps two headings of one kind, "Active and planned" and "Finished", the latter folded (`SectionHeading` gained its own fold: `expanded`, `onToggle`) with its count and latest sprint beside it, replacing the gold "Finished sprints" line. Activity has no heading row (its table keeps the caption "Activity"). The milestone table's key column is headed "About" on the project and the workspace. The Sprints tab shows its count ("Sprints 2"). Design files 02, 09, 11 and the README updated.

- Spend is written one way everywhere (sprint 62 slice 5, run through Foreman). One shared `ui/Spend` writes every amount in the mono number font, with the amount before its tokens ("$0.09 · 3.5K tokens"); a zero is blank in a table column or a list row (projects, sprints, finished sprints, the task list, activity rows, an Agent step line, a run's story line) and "$0.00" in a details row or a heading (Details, Overview, the Steps heading, a step's Spend). A run's story line now puts the amount before its tokens.

- The manager's replies are formatted (sprint 62 slice 6). A finished reply in the side bar is rendered with the shared `Markdown` component (lists, `code`, code blocks, bold, headings; no raw HTML), in the side bar's text size. A reply still arriving stays plain text with its cursor until it ends, so the thread does not reflow as marks arrive; your own messages stay plain. Proposal cards are unchanged.
- A running task's page uses one event stream (sprint 62, run through Foreman). It opened the project's stream and the sprint's, which repeated the project's events; it now listens to the project's alone through `projectEvents`, and reloads on an event about its task as before. The sprint page never had a second stream.

- A task an agent filed names the task it came from (sprint 62 slice 6). The task's Overview says "Filed by the developer while working on FOR-12", FOR-12 linking to the filing step on that task's Activity; `foreman task show` prints the same line; a task that no longer exists reads "a task that no longer exists". Served as `filed_from` on the task detail, read in `foreman/services/views.py` from the filing event's `filed_from_task_id` and `filed_from_run_id`. Tasks filed by a person or another system show nothing new.

- `foreman init` and Settings › Runners use the project's own roles and workflows (ADR-0024, sprint 62 slice 6, run through Foreman). `init` accepts a workflow the workspace defines, and run again on a project keeps the workflow it has, whatever its source. Runners lists the models roles use as each project resolves them (shipped, then the workspace's, then the project's), read through the definitions layer; a model only an override uses is shown and one no role uses is not.

- Every test report is read in full (ADR-0035 amendment, owner 2026-11-24). Foreman stopped at 200 report files of 32 MB at most. Foreman's own suite writes 272, one per test class, so its count left out about 400 Python tests and all the frontend's. Reports are now read a piece at a time, however many and however large.

- A step's details say what it did to the repository (ADR-0038, sprint 62 slice 4, run through Foreman).
  - An agent step that changed the branch records `engine.step_changes` (files with lines and kind, totals; main's changes brought in by a branch refresh are not counted). Its panel shows Changed: the files and lines, what they are counted against ("since attempt 1's commit c248621", "since main at 0db4ca5, where the branch began"), each file, five and then "Show all N".
  - An agent step's panel shows Session: "New", or "Continued from attempt N", which picks that run.
  - A landed merge records where main was, the commits it brought in and what they changed. Its panel shows Main before, Brought in and Changed.
  - Steps recorded before this show none of these rows. Spec 2.5's event list is amended.

- The Agent side bar on a task page is closed until you open it (owner, 2026-11-24). It no longer opens by itself while a step is in progress. Opened or closed, it stays as you left it on every task and on the next visit, remembered apart from the manager's side bar (ADR-0029 amendment).

- A task's Status says what it is doing and at which step (owner, 2026-11-24).
  - The sprint's task list and the task's Overview head the column and the row "Status", not "Stage": the board's columns are the stages.
  - "Running · Develop", "Paused · Develop", "Stopped · Develop", and now "Blocked · Test" for a blocked task. It used to say "Running, develop" and only "Blocked".
  - A step is named as Activity names it everywhere: "Stopped at Test" in the decision box, "· at Test" in Needs you.

- A task's Activity lists every record the engine kept on it (owner, 2026-11-24).
  - Blocks the engine made, such as "Default branch 'main' HEAD changed", were listed on the sprint's Activity but hidden on the task's own. A task's Activity now shows at least what its sprint's shows about it.
  - The engine's worktree clean-ups (other tasks' worktrees removed to stay under `max_live_worktrees`) are the project's records, not the task's that needed the room.
  - A sprint's Activity does not list the sprint's own finish and tag: those are in its State and in the project's Activity (ADR-0037, decided).
  - A long unbroken value in a Details list, such as a full commit id in a block's reason, breaks inside its column instead of running past the page's edge.

- A record belongs to a run, a sprint or the project (ADR-0037, sprint 62 slice 3).
  - A sprint's records (it started, finished, is ready to finish, was tagged) and the project's (a command naming no task, a pruning) are no longer pinned to a task through a made-up run. Schema version 29 moves the old ones and deletes the 22 made-up runs in the live database.
  - A sprint keeps its tag when its first task moves to another sprint. Its records are never pruned, and are deleted with it.
  - An active sprint whose every task is done or cancelled says "Ready to finish" in State.
  - The project's Activity says a finished sprint's tag on hover ("3 tasks merged, tagged checkpoint-… at 6f79f4a"), or "Finished, not tagged" with why.
  - Spec 2.5 is amended: `run_id` and `task_id` may be empty, and `sprint_id` is added.

- The sprint's head, after the owner's look (2026-11-23).
  - The Tag and Note rows are gone. State says "Finished 20 Nov at 6f79f4a", with the tag's name on hover, or "Finished 20 Nov, not tagged", with the reason on hover.
  - The goal shows as many lines as fit beside the Details, instead of always four.
- "No code browser" is no longer a rule. A view of the code and one of the repository's history are open questions among the views of owner direction 6.

- A finished sprint is tagged, as spec 6.4 says (ADR-0036, sprint 62 slice 2).
  - Whether a user finishes it (dashboard, `foreman sprint complete`, a manager's proposal) or Foreman does, the default branch's head gets an annotated tag `checkpoint-YYYYMMDD-<sprint-title>`; a name already taken gets `-2`.
  - With the new setting "Checkpoint note" (`write_checkpoint_notes`, Settings › General › Advanced), a note of the goal, the tasks done and cancelled, and the follow-ups agents filed is committed to `docs/checkpoints/<tag>.md` first.
  - Both are pushed where merges are pushed.
  - The sprint's Details show the tag and the note. `foreman sprint complete` prints them.
  - A tag that could not be made leaves the sprint finished and says why ("Not tagged: …").

- A test step's result reads the same everywhere (owner, 2026-11-23).
  - The task's Overview says "Passed · 1,221 tests in 1 min 54 s" on its Test row, as Activity does.
  - The Checks tab's Tests detail is the sentence the step's log ends with: "186 tests passed in 2 min 58 s at 6332732", or "3 of 186 tests failed (exit code 1) in 12 s at 6332732" followed by the failed tests by name (up to 50, then "and N more").
  - The output's last line (the lone "OK") is no longer shown there.
  - The report reader keeps the failed tests' names.
- Foreman's own test command writes JUnit reports, and unittest-xml-reporting is in the dev dependencies, so a task's working copy has it.

- Foreman counts the tests (ADR-0035, sprint 62 slice 1).
  - It names an empty directory in `FOREMAN_TEST_REPORT_DIR` for each test run.
  - A test command that writes JUnit XML reports there tells Foreman how many tests ran.
  - A test step then reads "Passed · 1,599 tests, 1 skipped" in a task's Steps table and in its facts, and "1,599 tests passed (1 skipped)" in its story.
  - The Checks tab's Tests row says the count and no longer shows the output's last line (the lone "OK").
  - `engine.test_run` carries `report`, the API serves `facts.tests.counts` and `runs[].tests`, and `foreman` prints the counts with the event.
  - A report that declares a document type, is over 32 MB or is a link is not read.
- A built-in step's records are saved as they happen. The test step's start is recorded when the tests start, and their output while it prints.

### After sprint 61

- The dashboard's tab icon is the F of the wordmark (owner, 2026-11-22): Fraunces at weight 600, as the "Foreman" in the top bar is set. It used to be a drawn block F that matched nothing on the page.
- The task's Overview no longer ends its Steps table with "Every step and what it did is under Activity" (owner, 2026-11-22): the Activity tab is beside it.
- A task's pages say things one way (owner, 2026-11-22).
  - **Overview:**
    - The checks summary is gone; the Steps table and the Checks tab say it.
    - Details shows everything at once, with no "More details" and no "Times at each step" (the Steps table's Attempts column says it). The working copy and the tokens show only when there are some.
    - The description and the acceptance criteria are formatted as written (lists, `code`, bold), one line per line.
    - In the Steps table, a gate the setting decided reads "Approved by setting" in no colour, Merge reads "Merged" without "in 0.1 s", and the count column is "Attempts".
  - **Checks:**
    - It reads "Measured by Foreman".
    - The review is named by its role, without its APPROVE line.
    - Criteria show formatted, and no longer repeat "Code review approved …" on every row.
    - "Evidence files" shows only when there are some.
  - **A step's facts** say who decided a gate in the Details' words: "Foreman approves merges (project setting)".
- A task's Activity table lists the task's own steps (owner, 2026-11-22), headed "Steps" with their count. It leaves out the step that closes a task after its merge, and the engine's records that do not name the task: a sprint ready to finish, the engine resumed or shut down while another task ran, the default branch moving. An engine record that names the task (its step stopped or paused during it) stays, as "Interrupted". A step tried again says "attempt 2" after its name. A step that made a commit says "Committed". A gate the project's setting decided says "Approved by setting", in no colour. The Commit column names the commit each step was about, including the one tests ran on and the merge commit. `GET /tasks/{id}/runs` returns those steps with `attempt` and `step_commit`. The task's Overview no longer counts runs ("Spend" is money; "Every step and what it did is under Activity").
- A task's picked step has one shape for every kind of step (owner, 2026-11-22, from a mockup). The left side is what happened, in order: each line is a time, what happened in plain words, and what it ran, wrote or printed. An agent's step begins with "Sent the prompt · N lines", folded like any command. The right side holds the step's facts: Result, Why, Decided by, After, the commit it was about (Tested, Reviewed, Merge commit), By, Model, May use, Took, Spend and Next. After and Next pick the neighbouring step in place. One button downloads the whole transcript (prompt, every event, raw output). The step's bookkeeping is no longer in the story: "Started…", "…ended", "Next step", the model and tool lines, the agent's command line, usage-limit notes that allowed the run, events with no words, and JSON. Agents' words are formatted and lose their APPROVE, STEER and TASK_COMPLETE markers. A refused tool reads "Not run: this role may not use Bash". A gate the project's setting decided says so: "Approved without asking anyone", decided by the setting "Approve merges". This replaces "Show the raw output", "Show the prompt" and "No prompt was recorded". The Agent side bar's story follows the same rules.
- A run's story treats long text by one rule (owner, 2026-11-21). What an agent or a user wrote is shown whole; it used to fold after twelve lines on screen, so whether a message folded depended on the window's width. A command the agent ran, a tool's result, test output and a merge error show their first three lines with "Show all". Before, a tool's result and a merge error were cut to three lines with no way to open them, test output scrolled in a box of its own, and a long command was shown whole. This applies on the task's Activity and in the Agent side bar.
- The sprint page's top is redesigned (owner, 2026-11-21, from a mockup). The goal shows four lines, then "Show all", beside the sprint's Details (state, tasks, spend), as a task's Overview does. Below are two tabs: Tasks, as a list or a board, and Activity at its own address (`/sprints/{id}/activity`). Each tab's controls are on the tab line, at its right: Add from backlog, New task and List | Board on Tasks; By and All | Problems on Activity. By filters what one role, Foreman or users did (`GET /sprints/{id}/activity?by=`, with the roles present in `who`). On every activity list and on a task's Steps, By names the role ("Developer", "Code reviewer"), with the model on hover. The outcome line is off the sprint and project pages; the numbers stay in `foreman outcomes` and the API, and a statistics view is in the backlog (ADR-0034 amendment).
- The sprint's Activity gives the task's title more room: the Key column is as narrow as the task list's (72px, from 120), and What happened, By, Took and Spend are sized to what they hold. The title gets 496px, up from 392px. A title still longer is cut, all of it on hover.
- "User", not "person", wherever Foreman names someone (owner, 2026-11-21): the dashboard ("A user approves merges", "Asked a user"), CLI output, API refusals, the gate role's label, and the guidance an agent is given ("## Guidance from a user"). A recorded actor that is only a channel ("dashboard", "cli") shows as "a user". API field names (`person`, `people`) are unchanged.
- The project's Activity lists every change of the engine's state, its starts too, so a stop is never followed by another stop; a dashboard Start names who started the engine. The sprint's Activity has a Key column like its task list, the project's a sprint-name column, and the headings no longer repeat the tab ("Sprints and engine", "Runs"). The "Finish sprints" hint says that a sprint a user finishes leaves the next one waiting to be activated.
- Activity redesigned after the owner's review (owner, 2026-11-21). Every activity list is one table shape, one line per row with the same column widths: When, the subject (sprint, task or step; its title cut at the same width everywhere), What happened, By, and numbers where the level has them. Reasons are on hover and on the page a row opens. Each level lists its own things: the project and the workspace list sprints and the engine; a sprint lists what happened to its tasks, including closes, cancels and unblocks by hand, from `GET /sprints/{id}/activity` (which replaces `/runs`); a task lists its runs. Milestones lose the task kinds and the per-merge numbers, and an engine that stopped is one row at its stop. Paged lists read again while the page is open, so project Activity no longer goes stale. The outcome line is one short sentence.
- The engine no longer starts a planned sprint on its own (owner, 2026-11-21, ADR-0025 amendment). A sprint created while the engine runs stays planned until a person activates it, so it is not started before its tasks are planned; after a person finishes a sprint, the next one waits for "Activate sprint" too. Foreman finishing a sprint (`sprint_completion = auto`) still starts the next, and Start on the engine row still activates the first planned sprint when none is active. The engine row says "no sprint is active" when that is why nothing runs.
- Outcome numbers read timestamps ending in `Z` on Python 3.10, which the CI runs alongside 3.12. Before, 3.10 could not read them, so a merge's time, the median wait for a person and the median time to merge came out empty there.
- Project Activity and the workspace's Recent say what a lead needs to know. New milestones: a task blocked (by the engine, its agent, a visit limit or a step with no way on, with why), unblocked, closed by hand or cancelled (by whom, why), a person's decision at a gate, a plan confirmed (by whom, its reason). A merge says how it got there: "after 1 send-back (review) · 15 min · $0.45" or "first time". An engine's start and stop are one row ("Engine ran 21:33–21:59 (26 min), stopped by masis"); one that died or was killed reads "Engine stopped without a word" and is listed under Problems. Filters: All, Sprints, Merges, Problems, Engine. The `engine_started` and `engine_stopped` kinds are replaced by `engine_run` and `engine_lost`.
- The sprint page's Activity is built from runs (`GET /sprints/{id}/runs`): one row per step of each task, newest first, saying who did it, how it ended and why, how long it took and what it cost, with a filter for send-backs and failures. Steps that only keep a record (filing, marking done, the engine's own records) are left out. It used to list bare step events ("Merge approval · Approve", "Done · Success").
- Activity reads the same everywhere (owner, 2026-11-21). A run's words come from one place: a review that sends a task back says "Sent back" with the reviewer's reason in its row, not "Steer"; the engine's own steps are by "Foreman"; a filed task names who filed it; a gate the project setting decided says so; durations read "4 min 22 s". The task runs API carries each run's `outcome_detail`.
- Every activity table names its columns and every row leads somewhere: a milestone to its sprint or task, a sprint step to that run on the task's Activity (`/tasks/{id}/activity?run={run}` opens with the run picked). Milestones show the time as well as the day. Overview says when a step passed after sending the task back ("Approved after 1 send-back").
- The outcome numbers (ADR-0034) are on the dashboard: one line at the top of the project page for all sprints, and one under the sprint page's summary for that sprint. The line shows first-time passes, send-backs by cause, what you were asked and did, cost per merged task and time to merge, with a table by role and model behind "By role and model".
- A decision counts as waiting only while its task is open. A task closed or cancelled at a gate used to stay "waiting" in the outcome numbers forever (ADR-0034 amendment).

### Sprint 61 — the core, proven

- Closed on 2026-11-20. Assay's sprint 2 was planned by its manager, confirmed by the owner, and run by `foreman serve` with merges approved by Foreman: 8 of 8 merged, 7 first time, $0.36 per merged task, and nobody stepped in. No Foreman fault was seen, so this sprint has no fix from it.
- Every read command takes `--json`, and its text and its JSON come from the same service read (ADR-0032): `status`, `board`, `project`, `cost`, `history`, `transcript`, `task show`, `worktree list`, `token list`, `notify list`, `notify deliveries`, `roles`, `workflows`, `role list/show`, `workflow list/show` and `db version` gained it. The worktree list, tokens and notification channels are now read by the same code as the dashboard's API. The existing `--json` documents are unchanged.
- The seven functions over 200 lines are split into named parts, with no change in behaviour (ADR-0032): the agent step and its corrective retry now share one execute-and-record, the native runner's stream is folded by one tally, and the resident engine's loop keeps its state in one object. No function in `foreman/` is over 200 lines.
- A run left `running` by an engine that died is recovered at its step, not at the start of the task. The task keeps its step, what that step was handed and its visit counts; the step runs again, and a developer resumes the session the dead run recorded (a reviewer, which keeps no session, reviews afresh). It used to be reset to the entry step with its counts cleared, so an engine that died during review had the developer do the task again.

- A corrective retry (a developer that ended without its completion marker, a reviewer whose verdict was malformed or that approved a cut diff unread) resumes the agent's session and now sends the correction alone. It used to send the whole first prompt again with the correction after it, into a session that already held it, and the developer started the task over.
- A task lease's fencing number is checked on every task write the engine makes (ADR-0011 amendment). An engine whose lease on a task was taken over by another one used to learn it only at its next renewal, so a step that ended without one wrote the task over the new holder. The store now refuses that write in the same transaction, and the engine stops without touching the task, as it does when a renewal is refused. A lease that only lapsed, with nobody taking the task over, does not stop the write.
- `foreman outcomes <project> [--sprint ID] [--json]` and `GET /api/v1/projects/{id}/outcomes` show how well a project's agents do (ADR-0034): tasks that passed first time (and leaving merge conflicts aside), send-backs by cause (tests, review, a person, merge conflict), decisions a person was asked for and how long they waited, times a person stepped in unasked, cost and tokens per merged task, median time to merge, and the same per agent role and model. Computed from the recorded runs and events; nothing new is stored. The manager can run it.

### Sprint 60c — defaults from a terminal

- `foreman role` and `foreman workflow` (`list`, `show`, `set`, `reset`) take `--workspace` in place of a project to work on the workspace's default roles and workflows (ADR-0024 amendment). Naming a project works as before; naming both or neither is refused. A role saved as a workspace default still goes through the model check, and a refused save prints why and exits 1.

### Sprint 60b — engine findings of the supervised run

- The developer prompts forbid the system Python where the repository names a virtual environment. The fixed line "Use only ./venv/bin/python and ./venv/bin/pip" is replaced by the prompt variable `{environment_rules}`: when `AGENTS.md` names `./venv` or `.venv`, it forbids `python`, `python3` and `pip` from the system for anything, one-off scripts included, and names that environment's binaries; otherwise the prompt says nothing about Python. A role text without the placeholder still renders.
- A branch behind the default branch is updated and tested again before it is merged (ADR-0026). The merge step used to merge a branch without asking whether it contained the default branch's head, so what landed had not been tested or reviewed. Now it merges the default branch into the task branch in the task's own worktree, ends with the new outcome `updated` and an `engine.branch_sync` event (step `merge`), and the three shipped workflows send `updated` to the test step. A conflict gives `conflict` as before. A project's own workflow needs a `merge` + `completion:updated` transition, or the task blocks.

### Sprint 60 — what is there works and makes sense

- A finished sprint can be reopened ("Reopen sprint" on the sprint page, or `foreman sprint activate`), when no other sprint is active; a cancelled one cannot (sprint 60 decision 8, ADR-0025 amendment). In the backlog, Decline is the one way to say "we won't do this": an accepted backlog task's More menu offers Decline where it offered Cancel. The API still cancels a backlog task, since a confirmed split cancels the task it replaces.

- "Finish sprints: A person / Foreman" in Project settings, beside "Approve merges" (sprint 60 decision 5, ADR-0025 amendment). With Foreman, the engine finishes a sprint once every task is done or cancelled and starts the next one. The setting is `sprint_completion` (`human` by default); the autonomy level, which nothing could set, no longer decides it.

- The "Developer (worker fleet)" role is removed (sprint 60 decision 3). No workflow used it; it only pointed a developer at another model endpoint, which any role does with `[agent.env]` (MANUAL §9).

- A task finished before the judge was removed shows its criteria as covered when its approving review was of the branch head; its stored evidence said "unverified", which meant that no judge had looked.

- The criteria judge is removed (sprint 60 decision 1, ADR-0010 amendment). It never ran, since no page offered its endpoint. An approving code review of the branch head covers the acceptance criteria, and the task's Checks say "Covered by review"; until then "Not reviewed yet". Its four settings and `judged_by` are gone, and the merge waiver for partly met criteria went with it, since nothing produces that failure any more. Evidence the judge recorded still loads.

- A note is for the developer (ADR-0033, sprint 60 decision 6). A note written on a task is delivered only to the agent doing the work, at its next step. A reviewer is shown every note as context, with whether the developer has had it, and is never delivered one; before, a note written while a task waited for review went to the reviewer as instructions. The task page says "Save for the developer".

- The test command is edited in the dashboard (Project settings, General, Tests), the owner's decision (ADR-0017 amendment). It is no longer a host-level setting; the others stay terminal-only. An edit that empties it is refused, since the test step fails without one.

- The five longest modules are split by concern (ADR-0032): `engine/builtins` (run tests, merge, the completion guard, mark done), `engine/orchestrator` (a project pass, one task, resuming from a gate), `engine/workflow_runner` (the loop, checks, built-in steps, agent steps, transitions), `engine/resident` (the loop, the command table, waiting, `serve_project`) and `cli/tasks` (by kind of command). Each class is put together from its parts and imported from where it was. No behaviour changed. The longest module is now the append-only migrations list.

- One implementation of each change (ADR-0032). The CLI and the dashboard each had their own copies of adding a task to a sprint, creating a sprint, registering a project, changing a setting and pruning worktrees, and their rules had drifted. Each is now one operation in `foreman.mutations`, which both call. A test (`tests/test_layers.py`) fails if the CLI, the API or a service saves or builds a project, sprint, task, decision gate or merge waiver itself. Behaviour that changes: `foreman sprint add` follows the sprint rules (an empty title is refused); the dashboard's Run activates the next sprint through the sprint rules; `foreman task override` checks overrides as an edit does; a task's or sprint's id is made from its title by the one slug function.

- The backend in layers, slice 5 (ADR-0032), the last of the plan. `notifications` is a package split by concern (`policy`, `destinations`, `transport`, `delivery`). Of the 45 imports placed inside functions, three are left, each a late load of something heavy or platform-specific; the four `TYPE_CHECKING` guards are plain imports. Nothing but `__init__` and `__main__` is at the root of `foreman/`. ADR-0032 lists what the layers do not settle yet: the CLI does not go through the services, and five modules are still long.

- The backend in layers, slice 4 (ADR-0032). `DashboardService`, one class of 2,408 lines, is eleven services in `foreman/services/`, one per area, put together by `Services`. The six `dashboard_*` modules and `backlog` joined them, and `foreman/dashboard/` is `foreman/api/`. The import shim `dashboard_backend` is gone. The services' errors lost their `Dashboard` prefix (`NotFoundError`, `InvalidRequestError`, and so on), since the CLI meets them too. The bundle helpers are `api/assets`, so `api/runtime` and `api/app` no longer import each other. No behaviour or API changed.

- The backend in layers, slice 3 (ADR-0032): the manager's modules are one package, `foreman/manager/` (`agent`, which was `meta_agent`, `proposals`, `planning`, `digest`). The manager chat's routes import them at the top of the module, as every other route does.

- The backend in layers, slice 2 (ADR-0032). `Mutations` is a package with a part per area (`tasks`, `gates`, `backlog`, `sprints`) over `base`, composed like `ForemanStore`. A gate decision is written by `mutations/gates.py` for a person and for the engine alike, so the rules for a person's change no longer import the orchestrator, and the contract lists no exception. The writer of runs and events and the process log moved below both, to `foreman/history/`. No behaviour changed.

- The backend is built in layers (ADR-0032), slice 1. An `import-linter` contract (`.importlinter`, run in CI as `lint-imports`) states the stack, and an import that breaks it fails. The model and its rules moved to `foreman/domain/`, git, worktrees, the context projection and the scaffold to `foreman/repo/`, roles, workflows and the human-gate step rules to `foreman/definitions/`, and the engine's root modules into `foreman/engine/` (`serve` is `engine/resident`, `engine_lock` is `engine/lock`, `engine_control` is `engine/control`). The task lease heartbeat joined `engine/leasing`, so a lease is one module per layer instead of four. No behaviour changed, and logger names are the same.

- One look for containers and scrollbars (owner, 2026-11-18; the design README's "Look" is revised). A panel, in the tinted tone with the 3px radius, holds a group of things one may act on: Needs you, a task's decision, a board column, and now a manager's proposal, which was the one outlined component. An item on a panel is one step lighter (`--color-panel-item`, renamed from `--color-board-card`). Every scrollbar in the app, the page's own included, is thin and grey; before, only the board's were. The manager side bar has the page's ground, so a proposal in it reads as a panel; on the bar tone it barely showed.

- A sprint's board folds its columns (owner, 2026-11-18). A folded column is a narrow strip with its name read downwards and its count after it, and the count is gold when a task in it needs you. The caret at the end of a column's heading folds it, and the strip opens it again. An empty column starts folded, so a finished sprint shows Done with the steps beside it as strips. A person's own choice is remembered per project in their browser. "None" under an empty column is gone. Every open column is 272px wide, as Trello's lists are, and the board scrolls sideways when they do not fit. Done, open on its own, no longer stretches its cards across the page. The board fits in the window: a column with more cards than fit scrolls them under its heading, as Trello's lists do, so the sideways scrollbar is always in view. An edge where columns are cut off fades out. Before, a long column pushed the scrollbar below the window, and columns past the edge looked as if they had vanished. After trying five designs in a board lab with the owner, each column is now a panel (tinted, with cards one step lighter), as Trello's lists are, so a column cut at an edge reads as cut. The board is 160px taller than the room left in the window. Its scrollbars are thin and grey in the app's look, and a column's scrollbar sits in the panel's margin instead of against the cards.

- The manager's conversation, after what went wrong on Assay (ADR-0022 amendment, 2026-11-18):
  - **A reply is seen while it is written, by anyone looking.** The message and an empty reply marked `in_progress` are stored before the model is asked, and the reply is saved as it grows. While a reply is in progress, a new message, a supervision turn and clearing are refused. The side bar shows the reply with its cursor and reads the conversation again every 1.5 s while it is written (every 5 s otherwise). A dashboard that starts marks a reply left in progress as interrupted.
  - **The manager's process is killed when its turn ends.** A turn that failed on a long line used to leave it running, and it stored a proposal afterwards.
  - **Clearing the conversation declines its waiting proposals**, recorded as the person's decision. The dialog says how many. They used to stay waiting where nothing showed them.
  - **`ref` on `create_sprint` and `file_task`.** A later operation may name either by its ref wherever it takes a sprint or task id. One proposal can now create a sprint and fill it, where it took two confirmations.

- A new project starts with `merge_approval = human` and workers on `claude-sonnet-5-5` (found on Assay). `foreman init` gave `claude-sonnet-4-6`, an id no longer offered, and no merge policy, so the built-in `auto` merged without a person. A project added from the dashboard had no settings at all. Both now use `new_project_settings()`. Re-running `foreman init` on an existing project still sets no policy, and the built-in default of the matrix (ADR-0014) is unchanged.

- A project's folder on the default branch follows each merge (ADR-0031, amends ADR-0012). Before, the engine moved `main` under it and left its files at the commit before, so git listed the merged work as staged deletions (found on Assay). After a merge, `_builtin:merge` brings that checkout to the merge commit with `git read-tree -m -u` from the commit its index still shows, keeping untracked files and unstaged edits and refusing where it would overwrite one. It records `engine.checkout_updated` or `engine.checkout_behind` (with the reason). A checkout on another branch is untouched.

- Block exists only for a task that has not started (owner, 2026-11-18; ADR-0030 amended). A started task is stopped or closed. The task page no longer offers Block on a task in progress, so a running task has no More; `POST /tasks/{id}/block`, `foreman task block` and the manager's `block_task` refuse any status but `todo`.

- A list that shows more on request can be put back: "Show fewer" appears beside "Earlier steps" once more than the first page is shown, and alone at the end of the list. It applies to the activity of a sprint, a project and a task, the backlog, finished sprints and the dialog that adds backlog tasks to a sprint. There was no way back short of reloading the page.
- A task's Activity tab: pressing anywhere on a run's row shows that run under the list (only its time could be pressed); the picked row is shaded and its time is gold. A pick stays while newer runs arrive. The list is read again in place while the task runs: it was emptied and drawn again on every event, taking what was shown under it with it. A run that was not in the list opens into place, and what a picked run shows fades in. A file's row in the Changes tab is pressed the same way.
- Changing tab no longer redraws the page. Each tab of a task, a project, a sprint and the project settings was mounted as a new page, so the head went blank, the task (with its checks and changes) was read again, and then the tab's own data arrived: two redraws. The tabs of one thing are now one page and only what is under the tab bar changes.
- The window keeps room for its scrollbar, so the page no longer shifts sideways when a shorter tab fits the window and a longer one does not.
- Everything that opens more in place has one look: gold, in a control's size and weight, with a caret. That is "Show all" and "Show less" under a long description or acceptance criteria, the closed lines ("More details", "Finished sprints", a run's raw output and prompt, "Waits for"), and the buttons under a list that show the rest of it ("Show all 8", "Show more", "Earlier"). The words under a long text were in the text's own type and colour and read as one more line of it; the others were grey, some with a caret and some without.
- The manager no longer fails when something it reads is long. Its output was read with a 64 KB limit per line, and one tool result is one line, so reading a 71 KB specification ended the turn with "Separator is not found, and chunk exceed the limit". Found on the first project that is not Foreman.
- A task's actions are in plain sight (ADR-0030). Beside the title, what depends on the task's state is a button: Run next, Stop, or Reopen. Close ends a task by hand and asks how: "Not needed" (cancel) or "Already done" (mark done, with the reason). More now holds only Block, Split into smaller tasks and Delete; Unblock is no longer there a second time. A task the engine is running no longer offers Mark done, Cancel or Delete, which the API refused.
- In "Needs you", a blocked task's row says why it is blocked and the step it stopped at, and has an Unblock button; it showed the sprint's name and had no button. Its kind reads "Blocked". `GET /needs-you` items of kind `unblock` carry `blocked` (`reason`, `step`).
- "Needs you" rows start and end where the design draws them. The tinted surface has side padding by design; the rows added the table's own edge padding on top, so their words sat further in than the design's and the line between rows stuck out past them. The line between rows now runs from one edge of the surface to the other, as in every other list, and so does the highlight under the pointer; both stopped short at both ends.
- A task's decision bar has one shape: the question on its own line, its facts on the line below, the buttons to the right. Before, the facts sat beside the question when they happened to fit, so a blocked task was one line and a merge approval two, and the same bar changed shape with the window's width.
- On a task page the side bar is the conversation with the task's agents (ADR-0029). The top bar's button says "Agent" there and "Manager" on a project or a sprint. It lists the task's steps oldest first, each opening onto what the agent said and did; shows what a person told the agents where it was said; and has the one box to tell the agent something, with "Interrupt and tell it now" while a step is running. It opens by itself while a step is in progress. A running step's output is now followed as it is written, in the side bar and on the Activity tab; before, it was read only when a step started or ended. The box and the list of notes are gone from the Activity tab, which stays the full record. "Split into smaller tasks" takes the person to the sprint, where the manager answers. Fixed on the way: the side bar ended 45px below the window while the page was at its top, hiding the manager's Send button until the page was scrolled.
- Foreman starts backlog work, and acceptance is its permission (ADR-0028, spec §6.2 revised). Accepting a filed task used to change a status and nothing else, and nothing in the backlog ever ran without a person planning it. Now: with "Foreman starts backlog work" on (project settings, Task picking; `task_selection_mode = autonomous`), the engine runs what a person planned first and then takes the next accepted backlog task into the active sprint itself, up to a limit per sprint; the sprint says "Started by Foreman k of N". Work an agent or another system files that no person has accepted is a request: Foreman never starts one, and turning the setting on blesses none. Requests are listed apart, with Accept and one "Needs you" line per project, only in a project where Foreman starts backlog work; where a person plans everything the backlog is one list with Plan and Decline, and nothing asks to be accepted. A person planning a request accepts it. What a person files is never a request. A backlog task's own page has "Plan into a sprint" (it was a dead end after Accept). Removed: the mode in which the engine created an empty placeholder task for the agent to name and ignored the tasks a person had planned, and `signal.task_started`, which let an agent rewrite a task's title, type, branch and acceptance criteria.
- One place to tell a task's agent something: the "Tell the agent" box on the Activity tab, pinned to the bottom of the window under the agent's output. While an agent step is running it offers "Interrupt and tell it now" and "Save for its next step"; otherwise "Save for the next step"; a finished task has none. The separate "Guidance for the next agent step" box on Overview is gone, and what the agent was told is listed on Activity. The box added the day before sat below the whole output, screens down the page.
- "Interrupt and tell it now" (ADR-0011 amendment, migration 28). On a task's Activity tab, under the output of a step an agent is doing, a box to tell the agent something: "Interrupt and tell it now" stops that step and starts it again with the note, without pausing the engine or blocking the task; "Save for its next step" leaves the step alone. New engine command `steer_task` and `POST /api/v1/tasks/{id}/steer`. Fixed with it: guidance handed to a step that was then killed was counted as read and not given to the restarted step.
- A task's "Model for <step>" overrides are lists of the models the project has configured (its default, the ones its roles name, the known Claude models), with "No override" first. They were free-text boxes that took anything.
- A role is not saved with a model the agent program cannot run. When a save names a model the role did not have, Foreman asks Claude Code one short question with that model (`foreman/model_check.py`) and refuses the save with the program's own reason if it cannot: typing "minimax" is refused in about two seconds, where it used to be saved and then fail every task that reached the role. From the dashboard and from `foreman role set`. A model that runs costs a fraction of a cent to check; `FOREMAN_MODEL_CHECK=off` skips it. Codex roles are not checked.
- A role's model list ends with "Type a model id…" where it said "Another model", which read as the name of a model. In the workflow editor the chosen step's name, who does it and each ending's choice are one width, and the dialog is as wide as the graph and that column need.
- Workflow graph, after the owner's look: the way down from each step has an arrow tip like the lines that go back, and is drawn only where a task can take it; the drawing is as wide as what it says, so there is no empty band beside it; "Add a step" is a button beside the "Steps" label; the chosen step's dropdowns are as wide as their text.
- The workflow editor draws the workflow as a graph, the way git draws branches: the steps down a rail in the order a task goes through them, ending at Done, with a line beside the rail wherever a task leaves the order (back to an earlier step, or in blue ahead to a later one), and the same in a few words under each step ("fail ↩ 1", "approves ↪ 5"). Clicking a step shows that one step beside the graph: its name, who does it, where each ending leads, and Move up, Move down, Remove. The long list of every step's dropdowns is gone.
- The workflow editor is a sequence. A task enters at the first step and leaves after the last, done; the step that marks it done is the end of the list and no longer a row. The way a step ends well leads "on to" the step below it without being wired, and follows the order when steps are moved, added or removed. Every other way a step can end says where the task goes instead: "back to 1 · Develop", "ahead to 5 · Merge approval" or "stop and wait for a person". Choosing who does a step fills these in (on, and otherwise back to the last step that did the work). The tick for passing on what a step said is gone: an agent is told whenever a task did not simply move on. What is saved is unchanged in form; the three shipped workflows go through the editor and come out identical.
- A workflow is checked as a whole before it is loaded or saved (ADR-0027). Refused, with the step and the path named: a step nothing leads to, no step that marks the task done, a step from which the end cannot be reached, an end reached without a successful merge, a merge reached without the tests passing since the last change, a first step that cannot start a task. The loader accepted all of these before. The dashboard's "empty workflow" was one of them (develop, then done, which cannot finish a task); it is now develop, test, review, merge, done.
- The workflow editor shows how a workflow runs. The steps have a "Steps" label and column heads (Step, Done by); each step is numbered and the first is marked "start"; every way a step can end names the numbered step it goes to ("go to 2 · Test") or "stop and wait for a person"; the tick reads "and tell it what this step said". A step added with "Add a step" goes in before the step that marks the task done and joins the sequence: the step before it leads to it, and it leads on. Up and Down replace Earlier and Later.
- Workspace settings: the heading "Defaults for projects" is gone. It was a group label drawn exactly like the sections under it (Workflows, Roles) and beside it (Access), so nothing showed it stood above them. Workflows and Roles are sections of the page like the rest.
- A new role or workflow may start empty: "Start from" offers "An empty role" (a short prompt naming the task's variables and how to end) or "An empty workflow" (develop, then done) before the copies. It forced a copy of an existing one. A role's model is chosen from a real list (the project's default, the models in use, the Claude models, or "Another model" with a field for its id); the old field only suggested entries that matched what was already typed, so it looked dead. The Workflow tab words the merge step's new outcome ("the branch was behind and was updated"). `scripts/dashboard_shot.mjs` gains `--text`, `set:` and `select:`, and clicks inside the open dialog.
- Workspace settings, "Defaults for projects": the workflows and roles are edited there, with the editors a project has (Edit, New workflow, New role, Edit as text, Back to the shipped one). They were a read-only list that sent a person to a file. A change to a default reaches every project that keeps no version of its own, and is refused, naming the project, if it would leave one unable to load (ADR-0024 amendment, migration 27).
- Audit of every screen, first batch of fixes. A merged task shows what it landed: its Changes tab lists the files of the merge commit (it said "The branch changes no file yet"), and its Checks say "Merged into main" with the commit and the real size of the change (they said "114 commits behind main" and "0 files"). A person's approval at a gate is shown as a person's, not the engine's. A finished task no longer offers guidance or overrides that nothing would read. A cancelled task's checks are blank. "Approve plans" says what it now governs. Sentences that explained the interface to its reader are removed from section headings and empty states across the workspace, project, backlog, sprint, task and settings pages.
- Spec §6.3 and §6.4 revised, ADR-0025: the engine finishes a sprint only in an autonomous project. In a directed or supervised project a sprint whose tasks are all done or cancelled stays active until a person finishes it; a task added to it is run; a blocked task prevents completion at every level. Docs only; the code follows in sprint 60b.
- The architect role and the workflow `development_with_architect` are removed (ADR-0022 amendment). The role asked for a sprint's tasks while running as the first step of every task, and its approved plan reached nobody. Planning is the manager's now. Migration 26 moves a project that was on that workflow to `development` unless it keeps its own copy. Six roles and three workflows are shipped.
- Planning (ADR-0022 amendment). A sprint with a goal has "Plan this sprint" in its More menu: the manager reads the goal, the spec and the repository and proposes the tasks, each with what to change, acceptance criteria, a size and what it waits for. A task that has not started has "Split into smaller tasks": smaller tasks that replace it. Both open the manager's side bar and end in a proposal card that shows every task in full. Who confirms it is the project's "Approve plans" setting: a person, or Foreman, which confirms only a proposal that does exactly what was asked. New proposal operation `add_task` (a task straight into a sprint, with `ref` and `waits_for` between the tasks of one proposal).
- Dashboard: a project's roles and workflows can be edited (ADR-0024 amendment). Project settings has a Roles tab: each role's model, tools, how its run ends and where it is used, a form to change them and its prompt, and New role as a copy of one you have. The Workflow tab has Edit steps (name, who does each step, and the step that follows each way it can end; add, remove and move steps) and New workflow. Both have a text view of the TOML, "Back to the shipped role" for one the project changed, and show the API's reason when a save is refused. `PATCH /api/v1/roles/{id}`, which wrote into Foreman's own files, is gone.
- Roles: a prompt must say how the run ends. Saving a role whose prompt does not name each decision it may give (or its completion marker) is refused; before, the list of decisions and the prompt were unrelated and a mismatch only showed as an agent asked again on every run.
- Roles: `[agent.tools] none = true` gives a role no tool at all. The triage and frontier reviewers, described as having no tools, denied seven by name and still had the web tools and sub-agents; they now have none (the CLI reports an empty tool list).
- A project can have its own roles and workflows (ADR-0024). They are TOML text in the database, loaded over the shipped ones: a shipped id is replaced for that project, a new id is added. `foreman role list|show|set --file|reset <project>` and the same for `foreman workflow`. Every save is kept as a revision with who made it. A save is refused, with the reason, unless everything still loads: a workflow naming a missing role, a role change that breaks a workflow, a misspelt tool name (tool names were unchecked before) or an unknown backend. The engine picks a change up from the next task it starts. Migration 25. The settings page's claim that a project could override definitions "in its own repository" was false until now; the dashboard editor is the next slice.
- Sprint 60 re-scoped by the owner (2026-11-16): identity, roles of people and audit are dropped from it; the sprint is now an audit and repair of every screen and feature, the engine findings of the supervised run, and a second run with several tasks.
- The supervised engine run (slice 1) is recorded in `docs/sprints/current.md`: FOR-44 went from develop to a pushed merge; three things it found are in the backlog.
- Dashboard: a long value in a settings row (the file of a role or a workflow, a path under "This machine") wraps inside its row instead of running out of the dialog.
- Sprint 60 opened (2026-11-16): identity, roles and audit behind a seam; manager chat through the runner; first, one supervised run of the engine. See `docs/sprints/current.md`.
- The off-loopback manager chat messages, `--allow-remote-manager` help and related docstrings no longer call the manager session "full-access"; they say it reads the repository and runs foreman commands on this host. Wording only; enablement is unchanged.

### Sprint 59 — the engine can be left running again

- Sprint 59 is closed (2026-11-16): archived at `docs/sprints/archive/sprint-59-engine-left-running.md`, checkpoint at `docs/checkpoints/2026-11-16-sprint-59-closed.md`. No sprint is open; `docs/sprints/current.md` holds a proposed sprint 60.
- Manager: a proposal can mark a task done by hand (`complete_task`, with a reason) and reopen a closed one (`reopen_task`), and `edit_task` can change a task's size and what it waits for. The proposal card says "Mark done ... by hand, without running its remaining steps" with the reason under it. Same refusals as from the task page and the CLI. ADR-0022 amended.
- Tasks: a task's size, priority and what it waits for can be changed after it is filed. The Edit task dialog has Size, Priority and, for a task of a sprint that has not started, "Make it wait for other tasks"; `foreman task edit <id> --size ... --priority N --depends-on ID ... | --no-dependencies` does the same; `PATCH /api/v1/tasks/{id}` accepts `complexity` and `depends_on_task_ids`. A task cannot wait for itself, for a task of another project, or for one that already waits for it (directly or through others), and what a started task waits for cannot change.
- Dashboard: a run on a task's Activity tab reads as a story instead of a list of raw JSON. Each line is a time and a sentence ("Started Review", "May use: Read, Grep, Glob", "Ran npm test", "Searched for shortSha in frontend/src", "Tests passed in 187.1 s at c52648d", "A person approved. Next step: Merge"); what the agent said is shown as it said it; what a tool returned is three quiet lines under the line that asked for it; test output is one scrolling block. The engine's bookkeeping is left out, and an event the page does not know is shown by name with its facts. The agent's raw stream is behind "Show the raw output" and is fetched only when opened. `GET /api/v1/runs/{id}/output` now gives each event's facts in `data` and takes `?raw=true`.
- Manager: the manager's session can read the repository and run `foreman` commands, and can write only its proposal drafts under `.foreman/manager/` (FOR-42, ADR-0022 amendment). It is started without `bypassPermissions`, with a fixed tool set and permission rules, without the dashboard's environment and without the operator's MCP connectors. Checked against the real CLI: redirects, chained commands, variable prefixes, `sqlite3`, `python`, `git commit`, reads outside the repository and writes outside the drafts folder are refused. A proposal is now written to a draft file and passed by path, since the CLI refuses a heredoc that contains JSON.
- Agent sandbox, first cut (ADR-0023). A role's `[agent.tools] allowed` list is now passed to the agent CLI as its whole tool set (it was read and ignored); `code_reviewer` and `security_reviewer` ship with Read, Grep and Glob only. An agent process is started with a short list of host variables instead of the engine's whole environment, so the dashboard token, forge tokens, cloud credentials and the SSH agent stay with the engine; a project names extra variables in the host-level setting `agent_env_passthrough`. Agents no longer get the MCP connectors the operator set up for themselves (`--strict-mcp-config`): a check with the real CLI showed a three-tool reviewer still had document and drive connectors. Not covered: the process still runs as the engine's user with a shell and the network.
- Engine: a reviewer's approval is not accepted when the diff it was given was cut and it opened no file (no Read, Grep or Glob in the run). It is asked once to read the changed files and decide again; a second unread approval ends the step in error and the task stops for a person, with the reason. A diff that reached the reviewer whole can still be approved from the prompt. This is a role option, `approve_needs_reading` under `[completion.output]`, turned on for the four shipped reviewer roles.
- Engine: after a merge the default branch is pushed to the remote named by the new project setting `merge_push_remote` (`foreman config <project> --set merge_push_remote=origin`). It is empty by default, so nothing is pushed unless asked. It is a host-level setting (ADR-0017): shown under "This machine" in project settings, changed only from a terminal. A push that fails is recorded as `engine.push_failed` with the reason, and the merge stands.
- Engine: a merge a person approves while the engine is busy with another task is carried out within about ten seconds, not when that task's step ends. The running step checks, before it starts and on its ticks, for tasks waiting at their merge step and runs their merge and mark-done steps; anything else (a conflict that sends the task back to develop) is left for the queue. ADR-0011 is amended.
- Engine: a task asked for with `foreman engine run-task` (Run next in the dashboard) runs as soon as the task in hand finishes. A pass used to keep taking tasks off the queue until none was left, so the request waited behind all of them (38 minutes on 2026-11-12, until the engine was restarted). A resident engine's pass now ends between two tasks when a request or a command is waiting. A requested task that has been closed or blocked by the time its turn comes is not run, and the command says so.
- Engine: a Claude Code run that comes back without running a turn (seen on FOR-17: a resumed session returned in 36 ms with no text) is a failed attempt, not an answer. The same prompt is sent to the same session again, within the infrastructure retry limit, instead of the task being blocked for a missing completion marker. The correction sent after a missing marker now says not to write the marker when the work is unfinished; two recorded runs had written it while saying the task was blocked, and were taken as done.
- Engine: a run in a resumed Claude Code session is charged only for itself. The CLI reports the session's running total, which was stored as each run's cost, so a session resumed three times was counted about three times. Each run now records the total (`runs.session_cost_usd`) and its own share (`cost_usd`); the per-run cost gate and `--max-budget-usd` apply to the run's own share. Migration 24 corrects the runs already recorded (the reported figures remain in each run's events); on Foreman's own project this lowers recorded spend, since sprint 58's $106 included the repeats.
- Sprint 59 opened (2026-11-15), the first of Phase 5: engine defects found during sprint 58, a first cut of the agent sandbox, dashboard follow-ups. See `docs/sprints/current.md`.

### Sprint 58 — frontend rebuild

- Sprint 58 is closed (2026-11-15): archived at `docs/sprints/archive/sprint-58-frontend-rebuild.md`, checkpoint at `docs/checkpoints/2026-11-15-sprint-58-closed.md`. No sprint is open; `docs/sprints/current.md` holds a proposed sprint 59.
- Dashboard: a menu is as wide as its longest item (and at least as wide as its button) instead of a fixed 240px, so a short menu such as a task's More no longer opens with empty space beside its items.
- Dashboard: project settings and a task's overrides no longer reset their form in an effect after the first render, which could wipe an edit made in that moment (the likely cause of a frontend test that failed now and then, on CI at `a963ac4`). The form starts over only when different values are read.
- Tasks can be closed and reopened by hand. `foreman task done <id> --reason` (`POST /api/v1/tasks/{id}/complete`, "Mark done" in the task's More menu) marks a queued, unfinished or blocked task done without running its workflow; the reason is recorded and the task says "Marked done by hand, not checked by Foreman". `foreman task reopen <id>` (`POST /api/v1/tasks/{id}/reopen`, "Reopen") returns a done or cancelled task to the queue. In the More menu, Stop is offered only while an engine is running the task; a task left part-way with no engine on it offers Run next instead.
- Dashboard: the Steps table on a task reads "Running" at the current step only while the engine is on the task ("Stopped here" or "Paused here" otherwise). A menu whose button is in the right half of the window opens leftwards, so the task's More menu no longer runs off the page.
- Dashboard: a task part-way through its workflow reads "Running, <step>" only while the project's engine is on it. With the engine stopped or on another task it reads "Stopped at <step>", and "Paused at <step>" when the engine is paused on it. Before, every unfinished task read "Running" whether or not anything ran.
- Dashboard: a task's Overview is redistributed. Description and Acceptance criteria move to the wide column, capped at a readable line length, and fold to twelve lines with "Show all" when longer; Overrides for this task moves beside them under Details, with controls as wide as what they hold.
- Dashboard: a task's token line under More details fits on one line ("cached", not "read from cache").
- CI: an unused import in `foreman/dashboard_service.py` had failed the Python lint step on every push since 2026-11-13 (thirteen merges); removed. The linter is now run locally before each merge.
- Frontend: ESLint (`npm --prefix frontend run lint`, flat config with the React and React Hooks rules) and a CI step. Seven unused names it found are removed.
- `scripts/dashboard_shot.mjs`: capture any dashboard address with the installed Chrome, after clicking, hovering or typing. `docs/TESTING.md` gains "Checking the look" with the fifteen rules a frontend change is checked against. Sprint 58's state, the design README (the backlog is a page, not a tab) and ADR-0020 are brought up to date; engine defects found during the sprint are in `docs/sprints/backlog.md`.
- Dashboard: pages stay current on their own. Inside a project the project's event stream triggers a reload (once per burst, at most every 2 s, agent output ignored); the workspace reads again every 20 s; returning to a background tab reads at once. Forms keep what is being typed.
- Dashboard: project settings gain "Advanced" (merge branch, specification file, reviewer and judge limits, judge model) and "Working copies" (count against the limit, what each is for, Remove unused).
- Dashboard: a task's Details name what it depends on, its size and priority, with the rest behind "More details"; New task takes a size and, in a sprint, the tasks it waits for. `GET /tasks/{id}` returns `dependencies` with key, title and status.
- Dashboard: a sign-in page appears when the server asks for its access token; the token is tried before it is kept, and Sign out forgets it.
- Dashboard: add a project from the workspace; cancel or delete a sprint from More on its page; move planned sprints earlier or later in the queue (`POST /sprints/{id}/move`, one transaction).
- Dashboard: one audit pass over every page. Needs you, task counts, headings, numeric columns, the sprint board, the Checks tables, settings forms and the phone-width top bar now follow the same rules (`docs/prs/fix-design-audit.md`).
- **fix, Backlog is a button, not a tab** (`fix/backlog-is-a-button-not-a-tab`):
  listed between two tabs it was a link to another page that looked like a
  tab. Tabs change what the project page shows (Sprints, Activity); other
  pages of the project (Backlog, Project settings) are buttons at the top
  right of the title row, where a page's actions are.

- **fix, the task decision is one line when it fits**
  (`fix/decision-on-one-line-when-it-fits`): the owner asked why "Accept this
  task?" took two lines for two short facts. The question and its facts now
  share a line and wrap only when the facts are long, as for a merge.

- **fix, Backlog is back in the row under the project header**
  (`fix/backlog-in-the-project-navigation`): in the title row the owner could
  not find it. It is listed between Sprints and Activity again, with its
  count, and opens the backlog's own page.

- **feat, a run records the commit it left**
  (`feat/task-record-the-commit-each-run-left-so-task-steps-ca`): design 05
  shows the Develop step as "Committed b232eb1", but runs carried no commit.
  Migration 23 adds `runs.commit_sha`; the engine writes the task branch's
  head when an agent run completes. `GET /tasks/{id}` runs and
  `GET /tasks/{id}/runs` return `commit_sha`. Overview's Steps say
  "Committed <sha>" when a step's last run moved the branch, and Activity has a
  Commit column.

- **fix, the backlog is reached from the project's title row**
  (`fix/backlog-link-in-the-project-title-row`): the owner found the line
  under the sprint queue a strange way to reach it. "Backlog" with its count
  now sits in the title row beside "Project settings", where the project's
  other pages are linked from; the line under the queue is gone.

- **feat, the backlog is a page of its own** (`feat/backlog-is-its-own-page`),
  decided with the owner. It was a tab of the project page and also a step in
  a task's breadcrumb, and a tab is not a place. It is now a page below the
  project, the way a sprint is: its own title, breadcrumb "Project / Backlog",
  no project header above it. The project page has two tabs, Sprints and
  Activity, and links to the backlog with a line under the sprint queue. The
  tab name added to the breadcrumb by `fix/breadcrumb-names-the-project-tab`
  is taken out again: a tab never appears in a breadcrumb. The address
  `/dashboard/projects/{id}/backlog` is unchanged.

- **fix, the breadcrumb names the project's tab**
  (`fix/breadcrumb-names-the-project-tab`), reported by the owner. A backlog
  task's breadcrumb read "Project / Backlog / task"; clicking "Backlog" went
  to the project's Backlog tab, whose breadcrumb read only "Project", so it
  looked like the wrong page. On the Backlog and Activity tabs the breadcrumb
  now ends with the tab's name.

- **feat, folders in the Changes tab** (`feat/changes-folder-breadcrumb`),
  asked for by the owner. From ten changed files up, the list offers the
  folders directly inside the current one, each with its file count and
  lines; picking one narrows the list to it and a breadcrumb ("All files /
  foreman / dashboard") widens it again. The picked file stays picked when
  the list is narrowed and while a running agent is still committing, and a
  diff is read again only when the branch's commit moves, not on every event
  of a running task. On the Activity tab the run's title is the step alone;
  who ran it is a detail beside it.

- **fix, section titles on a rule; the Changes tab laid out side by side**
  (`fix/section-rules-and-changes-layout`), reported by the owner. A section's
  title sat above its content with nothing joining them. It now sits on a
  rule that spans the section; column headers moved to the faint row line so
  the two do not compete; a heading above a tinted surface has no rule. On
  the task page the Changes tab label lost its figures; inside, the heading
  is "Files" with the count and the totals, and the file list sits beside the
  picked file's diff in its own scrolling column, where before the diff
  appeared under the whole list.

- **fix, counts beside labels** (`fix/counts-beside-labels`): reported by the
  owner as "strangely aligned". "Needs you 0" and "Backlog 0" set the figure
  at the label's size one space away, so it read as another word of the
  label. A count is now a slightly smaller figure a fixed distance from its
  label, on its baseline; the distance is a margin, not a space character.

- **feat, a new task straight into a sprint** (`feat/new-task-in-a-sprint`):
  the owner pointed out that a task could only reach a sprint through the
  backlog. The sprint page has "New task" beside "Add from backlog"; it uses
  the existing `POST /sprints/{id}/tasks`. A person writing a task into a
  sprint has decided it is wanted and where it goes; work filed by agents and
  other systems still lands in the backlog (ADR-0021). With it: sprint rows in
  the project's list are one line (the goal is on the sprint page); the New
  sprint dialog no longer asks for "the sprint number" and says the sprint
  starts empty; the engine row says when the active sprint has no tasks.

- **fix, alignment and one link to the workspace** (`fix/top-bar-baseline`),
  four things the owner reported. The wordmark sat about a pixel below the
  breadcrumb; it is lifted onto the same baseline. In the engine row the
  label, the state and the sentence were at different heights; they share a
  baseline, and a status dot is inline so it no longer sets the baseline of
  the word beside it. The row highlight reached past the sides of its table;
  it stays inside, and the first and last cell of every table keep 8px of
  room so nothing touches its edge. The switcher's "All projects" entry and
  the "Workspace" label were second and third links to where the wordmark
  goes; both are gone, and the workspace page has an empty breadcrumb.

- **fix, the wordmark answers the pointer** (`fix/wordmark-answers-the-pointer`):
  it turns gold on hover and focus, like every other link. An earlier change
  removed that on the engine team's own initiative; the owner had only asked
  what the link did, and without it the wordmark did not read as clickable.

- **fix, the sprint list: hover, the empty Planned line, finished sprints**
  (`fix/sprint-list-hover-empty-planned-finished`), three things the owner
  reported. A row's highlight now reaches 8px past its first and last cell,
  so the status dot is not pressed against its edge. The line "Planned: None.
  When the active sprint is finished..." is gone; with nothing planned the
  queue shows only the active sprint. Finished sprints say how many there are
  and how many are shown ("Showing 10 of 53, newest first"), with "Show 10
  more" and "Show all"; the filter is a shortcut, not the only way to older
  ones.

- **fix, no flash of an id before a name**
  (`fix/no-flash-of-ids-before-names`): reported by the owner. Opening a
  project showed its id ("foreman") as the title and in the breadcrumb, then
  swapped in its name ("Foreman") when the request returned. Two causes: an
  id was used as the stand-in for a name not loaded yet, and every page asked
  again for what the previous page had just loaded. A name now shows as
  itself or not at all, and `useResource` keeps what each key last loaded
  (per API client) so a page starts from it and refreshes it.

- **fix, a plain wordmark and one way home**
  (`fix/plain-wordmark-and-one-way-home`): the owner disliked the drawn F and
  did not understand its gold square, and asked what the difference was
  between clicking the wordmark and clicking "Workspace" (none). The wordmark
  is now only the name, set in Fraunces. Inside a project the breadcrumb
  starts at the project; the wordmark goes to the workspace and the project
  switcher lists "All projects". The favicon lost its square too.

- **feat, a wordmark, icons and motion** (`feat/identity-icons-motion`): asked
  for by the owner and not delivered until now. The top-left word is a drawn
  wordmark (an F cut to the weight of the letters, with one gold square) that
  goes to the workspace and no longer lights up like a link. `ui/Icon` is a
  small set on one grid, used on Workspace settings, Project settings, the
  Manager toggle (now a quiet toggle), the engine's Start, Pause and Stop,
  New sprint, New task, and the project's location and branch.
  `styles/motion.css`: controls and rows answer the pointer, the running
  engine's dot breathes, menus and dialogs rise in, the manager slides in;
  all off under reduced motion. A favicon.

- **fix, the Needs you heading sits above its surface**
  (`fix/needs-you-heading-outside-surface`): reported by the owner. The
  heading was inside the tinted surface with the rows, which the design
  rejects: the surface holds only what there is to act on. With nothing to
  act on the surface stays and holds the sentence that says so (a first
  version removed it; the owner asked why, and it was put back). Checked in a headless
  Chrome screenshot, the first time a page of the rebuild was looked at.

- **feat, a proposed sprint order is in Needs you** (`feat/task-b1e9a964d00e`):
  `GET /needs-you` carries pending decision gates as `settle_order` items,
  the workspace counts them, and the workspace and project pages show them
  with Accept and Reject, so `/dashboard/legacy` is no longer needed to
  settle one.

- **built frontend bundle out of git** (`chore/frontend-bundle-out-of-git`),
  by owner decision: `foreman/dashboard_frontend_dist` is ignored and no
  longer committed. `foreman dashboard` builds it when it is missing or older
  than the frontend source (`FOREMAN_DASHBOARD_NO_BUILD=1` turns that off),
  serves a rebuilt bundle without a restart, and the API starts without it
  (the shell route answers 503 with how to build). CI builds it in the Python
  job and drops the freshness check. A release must run
  `npm --prefix frontend run build` before `python -m build`. Five sprint 58
  merges had been sent back for conflicts in the committed bundle.

- **fix, a review sees the whole change** (`fix/review-sees-the-whole-change`):
  the second sprint 58 task (1,310 changed lines) was approved by the
  reviewer in 7 seconds; the diff in its prompt is capped (16,000 characters
  by default) and nothing told it the rest was missing. Reviewer prompts now
  say that a truncated diff means reading the changed files in full first,
  and the built frontend bundle is marked `-diff` in `.gitattributes` so it
  does not use up the cap.

- **fix, a step cannot leave work in the background**
  (`fix/agent-steps-wait-in-foreground`): the first sprint 58 task was
  blocked with its work done. The agent's test run outlived Claude Code's
  120 s command timeout, was moved to the background, and the agent ended
  its turn to wait for it, which ends a headless step. The Claude Code
  runner now starts every step with background commands off and a 20 minute
  default command timeout (`HEADLESS_STEP_ENV`; a role's `[agent.env]`
  overrides it), and the developer prompts say a step ends when the message
  ends.

- **design reference** (`docs/dashboard-design-v7`): `docs/design/dashboard-v7/`
  is the UI reference (17 screens and a README with the rules), replacing
  `docs/mockups/foreman-mockup-v6.html`, which is kept as history. ADR-0020
  records the design and how the frontend is built (layout, routes, data
  hooks, the temporary `/dashboard/legacy` seam). `AGENTS.md`, `CLAUDE.md`,
  `README.md`, `docs/ARCHITECTURE.md` and `docs/TESTING.md` point to it.
  Sprint 57 is archived; its undecided slice 9 is in the backlog.

### Sprint 57 — structure

- **slice 2c, workflow runner** (`refactor/workflow-runner`): the step loop
  and its phases are `foreman/engine/workflow_runner.py` (`WorkflowRunner`).
  `foreman/orchestrator.py` is 832 lines (4574 at the start of the sprint)
  and holds the project pass, running one task under a lease, and resuming
  a human gate. No behaviour change.
- **slice 8, tests along the modules** (`test/split-orchestrator-tests`):
  `tests/test_orchestrator.py` (8279 lines) is 13 files named for what they
  cover, on shared fixtures in `tests/engine_support.py`; 31 copies of the
  same six fixture methods are gone. The same 1110 tests run. New:
  `tests/test_git.py` (13 tests of the git helpers, which had none of their
  own) and `tests/test_store_concurrency.py` (5 tests with a connection per
  thread: a lease raced for by eight engines has one winner, concurrent
  event writes all land once, tasks created at once get distinct keys).
- **slice 7, package data and one version** (`chore/package-data`): the
  role and workflow definitions and the scaffold template moved from the
  repository root into the package (`foreman/data/roles/`,
  `foreman/data/workflows/`, `foreman/data/templates/`) and are listed as
  package data. A Foreman installed from a wheel had none of them and could
  not load a role; it only worked from a source checkout. The version is
  stated once, in `foreman/__init__.py`; `pyproject.toml` and the API read
  it from there.
- **slice 6b, API handlers, typed bodies, project stream**
  (`refactor/api-handlers-off-loop`):
  - the 37 non-streaming handlers run on the thread pool; they blocked the
    event loop on every database call, so one slow request stalled the
    event streams of everyone connected;
  - write routes with a fixed shape take typed bodies
    (`foreman/dashboard/schemas.py`). A field of the wrong type is refused
    by name; `{"title": null}` used to create a task titled "None";
  - `GET /api/v1/projects/{id}/stream`: one event stream for a whole
    project across its sprints, resumable with `Last-Event-ID`. The loop it
    shares with the sprint stream is `foreman/dashboard/streaming.py`.
- **slice 6a, routed and versioned API** (`refactor/dashboard-api`,
  ADR-0019): the 40 API routes moved out of the application factory into
  `foreman/dashboard/routers/` (projects, intake, sprints, meta, gates,
  engine, worktrees, tasks, roles). The API is served under `/api/v1`, with
  `/api` kept as an alias; the frontend uses `/api/v1`. Every error,
  including unknown routes, bad parameters, authentication failures and
  bugs, is `{"error": "<sentence>", "code": "<kind>"}`; an unhandled
  exception no longer leaks as a bare 500.
- **slice 5, CLI package** (`refactor/cli-package`): `foreman/cli.py` (3915
  lines) is the package `foreman/cli/`: `parser` (the parser and `main`),
  `common`, and a module per command group (`projects`, `sprints`, `tasks`,
  `gates`, `monitor`, `engine`, `tokens`, `notify`, `worktree`, `catalog`,
  `db`). Each command adds itself with a `register_<command>` function; the
  829-line parser builder is 26 calls. New for an operator: `--json` on
  `projects`, `sprint list`, `task list` and `engine status`; and one error
  boundary, so a failure is one `foreman:` line with exit 1, a bug says it
  is one and exits 70 (`FOREMAN_DEBUG=1` for the traceback).
- **slice 4, one mutation service** (`refactor/mutation-service`):
  `foreman/mutations.py` is the single implementation of the changes a
  person makes to tasks (accept, block, unblock, cancel, delete) and sprints
  (lifecycle, delete). The CLI and the dashboard both call it. What changed
  for an operator:
  - every task change records an audit event (`human.task_accepted`,
    `_blocked`, `_unblocked`, `_cancelled`) with who made it and from which
    surface; CLI changes left no trace before;
  - a task an engine is running cannot be deleted, and a sprint holding one
    cannot be deleted (only cancel was guarded);
  - the dashboard refuses to complete a sprint that still has unresolved
    tasks and names them, as `foreman sprint complete` always did; cancel the
    sprint to abandon what is left;
  - `foreman sprint complete` on a planned sprint is refused (activate it
    first), following the same transition table as the dashboard.
- **slice 3, store package** (`refactor/store-package`): `foreman/store.py`
  (3213 lines) is the package `foreman/store/`: `base` (connection, write
  helper, migrations), `rows` (row to model), and a part per aggregate
  (`projects`, `sprints`, `tasks`, `runs`, `events`, `gates`, `meta`,
  `leases`, `commands`, `tokens`, `notifications`). `ForemanStore` is those
  parts together and its interface is unchanged. One behaviour change: the
  20 writes that opened their own transaction (leases, sprints, projects,
  gates, manager sessions, pruning, task delete) failed immediately when
  another process held the database lock; they now retry like the rest.
- **slice 2b, engine package, third cut** (`refactor/engine-collaborators`):
  the orchestrator now composes collaborators from `foreman/engine/`:
  `TaskWrites`, `Retention`, `SprintFlow`, `Recovery`, `TaskSelector`,
  `SignalHandler`, `AgentStepRunner`, `PromptBuilder`, `TaskWorktrees`. The
  750-line step loop is a 170-line loop over named phases
  (`_task_worktree_problem`, `_limit_reached`, `_run_human_gate_step`,
  `_run_builtin_step`, `_run_agent_step`, `_record_step_completed`,
  `_follow_transition`), with one `_block_at_step` where seven copies of
  "record a blocked run and park the task" used to be. No behaviour change;
  `orchestrator.py` is 1883 lines, from 4574 at the start of the sprint.
- **slice 2a, engine package, second cut**
  (`refactor/engine-leases-and-records`): `TaskLeases` (`engine/leasing.py`)
  owns lease tokens and heartbeats; `RunRecords` (`engine/records.py`) is
  the engine's only writer of runs and events; branch refresh and conflict
  guidance are functions in `engine/branch_sync.py`; prompt-context and gate
  helpers are in `engine/prompts.py` and `engine/gates.py`. No behaviour
  change; `orchestrator.py` is 3144 lines.
- **slice 1, engine package, first cut** (`refactor/engine-package`): the
  separable parts of `foreman/orchestrator.py` are now modules of
  `foreman/engine/`: `errors`, `results`, `limits`, `model_selection`,
  `output_contract` and `evidence` (`EvidenceBuilder`). No behaviour change;
  `orchestrator.py` went from 4574 to 3754 lines. `builtins.py` no longer
  constructs an orchestrator to build evidence.

### Sprint 56 — engine truthfulness

- **slice 11, vocabulary and settings** (`refactor/status-constraints`):
  - migration 20: the database refuses a task status, task type, task
    complexity, sprint status, run status or project autonomy level that is
    not in `foreman/models.py`, through triggers (SQLite cannot add a CHECK
    to an existing table without rebuilding it). A test fixture that used
    the task type `bug` was the first thing it caught;
  - engine code reads settings through one typed, validated accessor,
    `settings.settings_of(project)`; the per-module helpers that each
    repeated a default and a type coercion are gone. `runner_max_cost_usd`
    now defaults to 0 (the role's ceiling applies), which is what the code
    did and the manual said; the model said 1000;
  - removed code nothing called: the typed-events module
    (`foreman/events.py`, never adopted by the engine) and six unused
    functions.
- **slice 10c, autonomous mode** (`fix/autonomous-mode`):
  - an autonomous task now gets its own branch and worktree like any other.
    It had neither, so the agent ran in the operator's checkout, committed
    to the branch checked out there, and the merge step failed with "Task
    branch is not set" (found by the first tests written for this mode);
  - an agent that never sends `signal.task_started` no longer blocks the
    task: the gap is recorded once and review goes ahead, as spec §6.2
    describes;
  - nothing about the mode is kept in memory, so a restart mid-task changes
    nothing; the check no longer names the `developer` role, it applies to
    any role allowed to send the signal;
  - a task type or branch reported by the agent is checked before it is
    stored; one that is not acceptable is refused with `signal.rejected`.
- **slice 10b, resident engine** (`fix/resident-engine-commands`):
  - a one-shot `foreman run` answers engine commands while it holds the
    project: `pause`, `shutdown` and `stop_task` stop its step (they sat
    unread before), and it refuses a `run_task` with the reason;
  - a pause outlives the engine that applied it: a restarted engine starts
    paused, so the state every screen reads is the state the engine is in;
  - a `run_task` stays `acknowledged` until its task has run and is then
    completed with what happened (it was `completed` on being queued); one
    accepted by an engine that then stopped is run by the next engine;
  - an unexpected exception ends `foreman serve` with `stop_reason: crashed`
    and exit code 1 (the log said exit 0);
  - an idle engine wakes for a change to its own project's settings,
    sprints, tasks, commands or queued notifications, not for every commit
    by any process.
- **slice 10a, retries and quota** (`fix/retry-and-quota`): after an
  infrastructure failure the retry continues the session the failed attempt
  opened (it replayed the whole prompt before); a session id the backend
  does not know is dropped and the step starts a fresh session instead of
  failing three times on it; what a failed attempt had already cost is kept
  on the run. A usage-quota stop is decided by the CLI's rate-limit notice
  when there is one, and otherwise only by the CLI's own phrases, so an
  error that merely mentions "quota" or "rate limit" no longer pauses the
  engine.
- **slice 9, guidance delivery** (`feat/guidance-delivery`): a guidance
  note written for a task now reaches an agent. The engine appends every
  note no agent has received to the prompt of the task's next agent step and
  records `human.message_delivered` with the notes, role and step. The API
  answers `recorded` (it said `sent` while nothing read the note), says when
  a finished task means no agent will read it, and the task drawer lists
  each note as waiting or read.
- **slice 8, facts-based evidence** (`refactor/facts-based-evidence`,
  ADR-0018): completion evidence no longer has a score or a verdict. It
  records whether the tests passed and on which commit, what each reviewer
  decided and on which commit (new `engine.review_recorded` event), and what
  a judge model said about each criterion when one is configured. Tests or an
  approval that are about an older commit than the branch head fail the
  proof. The keyword-overlap criteria check is deleted: without a judge the
  criteria are reported as not checked. The task drawer shows these as rows
  of fact, and the reviewer prompts are reworded to match.
- **slice 3b, worktree self-heal** (`fix/worktree-self-heal`): the
  integration worktree aborts a merge a killed engine left half-done instead
  of refusing every later merge; a task tree found on the wrong branch is
  moved back only when it has no changes to tracked files, and is otherwise
  reported and left untouched (the checkout was forced before, which
  discarded such changes).
- **slices 4, 5, 6, built through Foreman** (approved at the merge gate and
  merged by the engine):
  - the test step's run detail opens with a result line ("Tests passed in
    114.2s (exit 0)."), and `engine.test_run` carries `duration_seconds`
    and the `head_sha` the tests ran against;
  - a new item waiting for triage is handed to the notification dispatcher,
    so the webhook channel hears about it under the same policy as other
    attention events;
  - the manager's operating contract names only commands and flags the CLI
    has, with a test that fails when the two drift apart.

- **slice 7** (`fix/completed-sprint-delete`): the sprint page offers
  Delete on a completed sprint; it compared the status with `"done"`, which
  no sprint ever has.
- **slice 2, crash-safe steps** (`fix/crash-safe-steps`): a workflow
  transition records the next step in the same write, so an engine that
  dies between two steps resumes at the next one instead of restarting the
  task; an unexpected error inside a step marks its run failed instead of
  leaving it `running` (which refused the task until the stale-run window
  passed); built-in steps record how long they took.
- **slice 3, default-branch check** (`fix/default-branch-check`): a task is
  no longer blocked because the default branch moved while it ran (an
  operator commit, another task's merge). It is blocked only when its own
  commits are on the default branch before the merge step. ADR-0012 amended.
- **slice 1, safe task writes** (`fix/safe-task-writes`): the engine no
  longer replaces a task's whole row. `update_task_engine_state` writes
  workflow state only and never a cancelled row; before every step the
  engine re-reads the task, adopts an operator's edits, and stops if the
  task was cancelled or blocked. A task cancelled while a step runs stays
  cancelled, its open run is settled, and it is not merged. A blocker
  reported by the agent stops the workflow instead of being overtaken by the
  completion marker.
- opened sprint 56 from Phase 2 of the 2026-11-10 finish plan; refreshed
  shipped role model ids (reviewers `claude-sonnet-5-5`, triage
  `claude-haiku-5-5`, architect and frontier reviewer `claude-opus-5-5`)

### Sprint 55 — baseline and host safety

- **completion-evidence diff stats from numstat**
  (`fix/task-parse-completion-evidence-diff-stats-from-git-numstat`): the
  evidence builder reads changed files and added/deleted totals from
  `git diff --numstat -z` instead of parsing `git diff --stat`. Paths with
  spaces and long paths are reported whole, binary files are listed as
  changed, renames are reported under the new path, and deletion totals are
  exact. The returned tuple shape is unchanged; its integer is now the
  changed-file count.
- **slice 6, gate decisions through the engine**
  (`fix/gate-decisions-through-engine`): `foreman approve`, `foreman deny`
  and the dashboard's Approve and Deny record the decision and leave the
  task at the step it leads to; the engine continues it. They no longer run
  workflow steps in the CLI or the web process, outside the engine lock.
  The CLI prints whether an engine is resident and the command to continue;
  the dashboard shows a notice when none is. A task paused at a human gate
  now releases its lease instead of making the engine wait it out.
  ADR-0011 amended.
- **slice 5, task lease lifecycle** (`fix/task-lease-lifecycle`): new
  `foreman/task_lease.py` renews a task's lease on a timer for the whole of
  `run_task`, so a built-in step longer than the lease (tests, worktree
  setup) no longer loses it and re-runs the developer; stale-run recovery
  inside `run_task` re-acquires the lease instead of expiring the one just
  taken; a task parked `blocked` by a loop, cost or time gate or a failed
  guard releases its lease.
- **token split** (`feat/token-usage-breakdown`): runs store input, output,
  cache-read and cache-creation tokens separately (migration 19,
  `TokenUsage`); `run_totals` and `task_run_totals` sum them; the API adds
  `token_usage` to runs and totals; `foreman cost` prints a `Token split`
  line and `foreman history` adds `in=`/`out=`/`cache_read=`/`cache_write=`;
  the task drawer, run history and sprint footer show the split.
- **slice 4, engine death** (`fix/runner-parent-death`): SIGHUP (a closed
  terminal or dropped SSH session) is handled as a shutdown like SIGTERM;
  on Linux every agent the engine starts is sent SIGTERM if the engine dies
  with no handler running (SIGKILL, out-of-memory kill, crash), so a
  full-permission agent no longer keeps working unobserved.
- **slice 3, cost control** (`fix/runner-cost-control`): the per-run cost
  ceiling is handed to Claude Code as `--max-budget-usd` so spend stops
  while the agent works; a run whose result has arrived is never reported
  as killed; a budget stop is recorded as a cost kill with its real cost;
  shipped roles carry ceilings of $2 to $30 in place of $1,000;
  `runner_max_cost_usd` now lowers a role's ceiling (it was documented and
  unused); a task or sprint cost limit of 0 means off instead of blocking
  every task; the runner stops reading at the result line, bounds the wait
  for exit, and kills process-group leftovers after a normal finish.
- **slice 2, host-level settings** (`fix/host-level-settings`): the dashboard
  API refuses changes to `test_command`, `worktree_setup_command`,
  `worktree_root`, `worktree_link_paths`, `context_dir`, `judge_base_url`
  and `judge_api_key_env` (403 naming the key and the `foreman config`
  command) and to a role's `backend` and `permission_mode`; the Settings and
  Roles screens show them read-only. Worktree removal deletes only git
  worktrees of the project's repository and never the root; other
  directories are listed as not owned and kept. Role files are validated
  before they replace the old one. Intake source URLs must be http(s).
  ADR-0017.
- CI: install setuptools before the editable install (first run failed in
  `tests/test_cli.py` on a fresh 3.12 virtualenv).
- **slice 1, browser-origin defence** (`fix/dashboard-browser-origin-defence`):
  new `foreman/dashboard_guard.py`; every `/api` request except intake is
  refused when its `Host` is not a trusted name (token-less binds), when its
  `Origin` is not the dashboard's own or an allowlisted one, or when the
  browser labels a write cross-site; request bodies must be declared
  `application/json`; `?token=` works on GET only; `/docs`, `/redoc` and
  `/openapi.json` are off. Closes the cross-site and DNS-rebinding routes to
  the settings API reproduced in the 2026-11-10 review. ADR-0016.
- **slice 0, baseline** (`chore/phase0-baseline`): merged the three operator
  UI fixes with the policy matrix and triage UI and rebuilt the bundle; added
  CI (`.github/workflows/ci.yml`: Python suite on 3.10 and 3.12, ruff,
  repo-memory validation, frontend tests and build, bundle freshness) and a
  ruff baseline with a `dev` extra; restored six completion-evidence tests
  that a lost class header had shadowed; replaced the 1,067-line
  `docs/STATUS.md` with a current snapshot (history preserved under
  `docs/checkpoints/`); added the 2026-09-08 reviews and the 2026-11-10 full
  review and finish plan; closed and archived sprint 54

### Sprint 54 — Phase 1 resident engine and intake

- opened sprint 54 from Phase 1 of the production readiness review with the
  live-run protocol (slices executed through `foreman run foreman`)
- **slice 1, resident engine**
  (`feat/task-add-foreman-serve-resident-engine-worker-with-a-project-engine-lock`):
  new `foreman serve <project-id> [--poll-seconds N] [--once]` keeps the engine
  resident — each pass runs `run_project` once, and an idle pass waits on
  `PRAGMA data_version` or the poll interval instead of exiting, so work queued
  by another process is picked up without a person pressing Run. New
  `foreman/engine_lock.py` enforces one engine per project through a lease with
  `resource_type="engine"` (no migration: the `leases` table already supports
  arbitrary resource types), renewed from a daemon timer thread on its own
  store connection; `foreman run` takes the same lock, so neither can start
  while the other is resident. A task whose execution raises is blocked with
  the error as its `blocked_reason` plus an `engine.attention_needed` event and
  the service continues after a backoff (5 s, doubling, capped at 5 minutes,
  reset after a clean pass); SIGTERM settles the active run as `killed`, leaves
  the task resumable, releases the lock, and exits 0. New `foreman/logs.py`
  emits JSON lines on stderr — `serve` never prints, and the orchestrator
  mirrors every persisted event to the same logger, levelled by family
  (`foreman.logs.event_log_level`): the narrative at INFO, the agent output
  firehose at DEBUG. Retention pruning and crash recovery are gated behind
  `run_project(maintenance=...)` so idle wakes stay cheap. Recorded as
  ADR-0011; `foreman run --json-logs` opts into the same log format.
- **slice 2, the engine command table and the `foreman engine` CLI**
  (`feat/task-add-the-engine-command-table-and-foreman-engine-cli`): migration
  15 adds `engine_commands` (`pause`, `resume`, `run_task`, `stop_task`,
  `shutdown`; `pending` → `acknowledged` → `completed`/`rejected`) with an
  index on `(project_id, status, requested_at)` and `ON DELETE CASCADE` from
  both `projects` and `tasks`. `ForemanStore` gains `enqueue_engine_command`,
  `list_engine_commands`, `next_pending_engine_command`,
  `mark_engine_command`, and `get_engine_lock`, the last returning a
  token-free `EngineLockView` (holder, acquired, heartbeat, expiry) so
  operator surfaces can see who holds a project without the secret that would
  let them release it. The resident engine drains pending commands before
  every pass and supplies the orchestrator with a new `command_poll`
  callback, called before every workflow step and on every `agent.tick`, so a
  `pause` reaches an agent that has been quiet for twenty minutes: the agent
  process group is terminated and the run settled as `killed` through the
  existing `_abandon_run` path (`gate_type="command"`). `pause` leaves the
  task resumable and the engine resident, idle, and still heartbeating its
  lock; `stop_task` marks the task `blocked` with `blocked_reason`
  "Stopped by \<requester\>"; `shutdown` releases the lock and exits 0. Every
  command records `engine.command_applied` or `engine.command_rejected`, and a
  starting engine rejects pending `pause`/`stop_task`/`shutdown` with
  `result_detail="no engine was resident"` while honouring pending `resume`
  and `run_task`. New `foreman engine
  status|pause|resume|shutdown|run-task|stop-task`, with `--by` defaulting to
  the OS user name and the command id printed. ADR-0011 amended to record the
  command table as the only control channel to a resident engine. The
  dashboard is untouched and moves onto the table in the next slice. Merging
  main's quota pause in also made the engine's long waits (a failure backoff,
  a quota reset) command-aware: they end early when a command arrives, so a
  `shutdown` is answered in seconds rather than after a six-hour quota wait,
  and a paused engine narrates `serve.paused` once at INFO and then at DEBUG
  the way an idle one does.
- **slice 3, the dashboard on the resident engine + dead-letter reporting**
  (`feat/task-rewire-the-dashboard-onto-the-resident-engine-and-report-dead-letter-tasks`):
  the dashboard no longer manages processes. `_RUNNING_PROCS` and its
  process-handle helpers are gone from `foreman/dashboard_service.py`; Run
  enqueues `resume` (plus `run_task` for a task-scoped start), Pause enqueues
  `pause` and changes no task status, and a task Stop enqueues `stop_task` for
  the engine to act on. New `GET /api/projects/{id}/agent/status` reports
  `resident`, `holder_id`, `heartbeat_age_seconds`, `paused`, `current_task`,
  and the last ten commands; new `GET /api/projects/{id}/engine/commands`
  lists the log. With no engine resident there is nobody to send `resume` to,
  so the service spawns a detached `foreman serve <project> --db <path>`
  (stdout and stderr appended to `.foreman/serve.log`) through an injectable
  `ServeSpawner` — the single-machine bootstrap, and the only process the
  dashboard starts. New `foreman/engine_control.py` holds the read-side
  derivations the CLI and the dashboard share, so the two surfaces cannot
  answer "is an engine resident", "is it paused", or "why is this task
  blocked" differently from the same database. Dead-letter reporting: a
  derived `blocked_kind` of `gate` (parked at a `_builtin:human_gate` step) or
  `engine` (loop limit, unhandled outcome, cost or time gate, branch
  violation, failure isolation, `stop_task`) on task payloads, `foreman task
  show`, and `foreman board`, with `blocked_gate`/`blocked_engine` counts on
  project summaries and `foreman status` — derived from the workflow
  definition, no schema change and no new task status. `foreman task unblock`
  now refuses only the `gate` kind, so an engine dead letter with a persisted
  resume step can be cleared instead of being mistaken for a gate. The
  frontend header shows "Engine: resident / paused / not running" with the
  heartbeat age, its stop control says Pause, and blocked cards carry the
  kind. ADR-0002 amended: the dashboard controls the engine only through the
  command table.
- `fix/keep-session-on-kill`: a run that is killed or interrupted (shutdown,
  lease loss, an engine `pause`/`stop_task`) keeps the backend session id
  announced by `agent.session`, and the native step records that id as soon
  as it is announced, so the resumed visit continues the conversation instead
  of re-reading the repository.
- **slice 4, one git worktree per task**
  (`feat/task-give-every-task-its-own-git-worktree`): the engine no longer
  changes what is checked out in the operator's repository. New
  `foreman/worktrees.py` owns a `WorktreeManager` per project: task worktrees
  live under `<repo>/.foreman/worktrees/<task-key-or-id>/` (relocatable with
  the new `worktree_root` setting), are created on a task's first develop
  visit from the existing task branch or a new one cut from the default
  branch, reused on every later visit, and removed by `_builtin:mark_done`, by
  `foreman task cancel`, by the dashboard's cancel and delete, and by
  `foreman worktree prune`. Migration 16 adds the nullable
  `tasks.worktree_path` so the CLI, the dashboard, and a restarted engine
  agree on where a paused task's work lives. Native role steps run with
  `working_dir` = the task's tree; `_builtin:run_tests` runs the test command
  there (the `engine.test_started`/`engine.test_run` events carry
  `working_dir`); the context projection is mirrored into the worktree's own
  `.foreman/` so the agent finds `context.md` where it works; the branch
  invariants check the worktree's branch; and the refresh-before-develop and
  conflict-recovery merges happen there. `run_task` and `resume_human_gate` no
  longer check a branch out in `project.repo_path` or restore one afterwards.
  `_builtin:merge` runs its `--no-ff` merge in a shared
  `<worktree_root>/_integration` tree pinned to the default branch — the
  operator's checkout only sees the ref move — and now also refuses a dirty
  task worktree, since uncommitted work there is not on the branch and would
  be silently dropped; both dirty-tree guards judge the task's own tree and
  never the operator's checkout. The "default branch did not move during a step"
  invariant stays. Worktrees survive human gates, quota pauses, review rounds,
  and engine restarts. New `foreman worktree list|prune <project>`; `foreman
  task show` and `foreman history` print the path and the dashboard task
  drawer renders it. `run_project` preflights once before leasing any task, so
  a repository whose worktree root is not ignored, or a git older than
  `git worktree`, fails with one clear message instead of mid-step. New
  `worktree_link_paths` setting symlinks ignored local tooling (`venv`,
  `node_modules`) from the operator's checkout into every new worktree, since
  a worktree is a clean checkout and the project's `test_command` needs it.
  `tests/test_cli.py` no longer reinstalls the package when the virtualenv
  points at a different checkout, and runs every CLI subprocess as
  `python -m foreman` with `PYTHONPATH` pinned to the checkout under test, so
  a suite run inside a worktree cannot repoint the operator's virtualenv.
  ADR-0012.
- **slice 4b, bounded worktree disk use and a per-worktree environment**
  (`chore/task-c68378a4e541`): the two follow-ups ADR-0012 left open. New
  `max_live_worktrees` (default 4, `0` disables) caps how many task worktrees
  exist at once; `worktrees.enforce_worktree_limit` runs from the engine
  immediately *before* it creates a tree, so the cap bounds peak disk use
  rather than its steady state. It never touches the integration tree or the
  tree of the task about to run, reclaims done/cancelled/unclaimed trees
  first and then the least recently used (measured by each tree's own git
  index mtime), and **never reclaims a tree with uncommitted changes** — that
  work is not on the branch, so removing it would destroy exactly the paused
  state worktrees exist to preserve. A reclaimed task keeps its branch and
  workflow position, has `worktree_path` cleared, and gets a fresh tree on its
  next visit; a project whose candidates are all dirty stays above its cap and
  records `engine.worktree_limit_exceeded` (with `engine.worktrees_reclaimed`
  and `engine.worktree_reclaim_failed` for the other outcomes). New
  `worktree_setup_command` (and `worktree_setup_timeout_seconds`, default
  1800) runs once inside each newly created tree with
  `FOREMAN_WORKTREE_PATH`/`FOREMAN_REPO_PATH`/`FOREMAN_WORKTREE_BRANCH`/`FOREMAN_DEFAULT_BRANCH`
  exported, so a tree builds its *own* environment instead of borrowing the
  operator's through `worktree_link_paths`; a marker in the tree's git admin
  directory (never in the tree, which would dirty it and block the merge)
  makes it run once and reprovision when the command changes. This repository
  now sets it to build a per-tree venv and editable install, and
  `worktree_link_paths` is empty — a task's `./venv/bin/python -m unittest
  discover -s tests` runs on that tree's own interpreter. The dashboard
  project screen gains the live tree count against the cap, the worktree root,
  and a Prune worktrees control, backed by new
  `GET /api/projects/{id}/worktrees` and
  `POST /api/projects/{id}/worktrees/prune`. ADR-0012 amended.
- **slice 5, the intake endpoint and API tokens**
  (`feat/task-add-the-intake-endpoint-and-api-tokens-v2`): Foreman can now be
  handed work by a system rather than a person. New
  `POST /api/projects/{id}/intake` files one task from a JSON body (`title`
  required; `description`, `acceptance_criteria`, `task_type` defaulting to
  `fix`, `priority`, `complexity`, `source`, `sprint_id`) and answers **201**
  with `created: true` for new work or **200** with `created: false` for a
  repeat, returning the task exactly as `GET /api/tasks/{id}` serializes it.
  Migration 17 adds `api_tokens` — named, per-project, revocable credentials
  with a scope list, cascading from `projects`, unique on `token_hash` — plus
  `tasks.source_system` / `source_ref` / `source_url` / `reporter` indexed on
  `(project_id, source_system, source_ref)`. New `foreman/api_tokens.py` is the
  only module that mints or hashes a secret (`fmn_` + 32 random bytes,
  SHA-256); the secret is returned once by `create_api_token`, printed once by
  `foreman token create <project> --name NAME`, and reaches no row, log line,
  or event payload. `foreman token list|revoke` complete the surface; revoke
  writes a timestamp rather than deleting, so old tasks' `created_by` still
  resolves. **Intake is idempotent on the caller's own key** `(project,
  source.system, source.external_ref)` — the caller is what retries, so a
  re-delivered webhook is one task, returned unchanged. **The intake queue is
  a sprint**: work filed without `sprint_id` lands in `<project>-intake`
  ("Intake queue"), created on first use, `active` when no sprint is running
  and `planned` when one is, reactivated once that sprint finishes — sprints
  stay the unit of grouping and a continuous queue is a sprint that never
  completes, so no consumer needs a code path for a sprintless task. The two
  credentials are kept apart in both directions by the token middleware: the
  shared dashboard token is refused on intake, and an `fmn_` token is refused
  with 403 on every other `/api` route whether or not a dashboard token is
  configured. Auth outcomes are now service errors (`DashboardAuthError` 401,
  `DashboardPermissionError` 403) so the transport maps status codes instead
  of deciding them. Tasks carry `source` in their serialization and the task
  drawer shows the system, the reference (linked when a `url` was sent), and
  the reporter; filing emits `intake.task_created` on a synthetic `intake` run
  carrying the source and the token's id and name. Recorded as ADR-0013 and
  documented in MANUAL §25. (The task specified migration 16 and ADR-0012;
  both were taken by slice 4, so this landed as 17 and ADR-0013.)
- **slice 6, the policy matrix**
  (`feat/task-add-the-policy-matrix-triage-plan-merge-and-notification-decisions-v2`):
  autonomy is now a policy, not a mode. New `foreman/policy.py` owns four
  decisions — `triage` (`auto`/`human`, default `human`), `plan_approval`
  (default `human`), `merge_approval` (default `auto`), and `notification`
  (`none`/`attention`/`all`, default `attention`) — each resolved from three
  layers, most specific first: the task's `executor_overrides` (`policy`, or
  the older gate-only `gates`), a rule for the task's type from the new
  `policy_rules` setting (`{"<task_type>": {"<decision>": "<value>"}}`), then
  the project default setting, else the built-in. Nothing else resolves a
  policy: `ForemanOrchestrator._gate_policy_decision` delegates to the matrix
  and `DashboardService.intake_task` asks it for the arriving status.
  **Resolution reports its source**, and every task's first step writes one
  `policy.resolved` event carrying all four `(value, source)` pairs
  (`task_override`, `task_type_rule` plus the type, `project_default`,
  `built_in_default`), so the audit trail says *why* a person was or was not
  asked; a new `ForemanStore.has_event` keeps it to one per task across
  resumes. Settings are **strict on write** (`ProjectSettings` refuses an
  unknown task type, decision, or value, so `foreman config --set
  policy_rules=…` fails at the typo) and **lenient on read** (a stored value
  the matrix does not recognize is dropped for the built-in default rather than
  stopping a run). New task status **`triage`**: work filed through intake
  under a `human` triage policy lands there instead of `todo`, where
  `select_next_task` never sees it, and raises one `engine.attention_needed`
  turn with trigger `triage`; `foreman task accept <task-id>` and
  `POST /api/tasks/{id}/accept` move it to `todo`, and `task cancel` works from
  it. New `GET /api/projects/{id}/policy` returns the defaults, their sources,
  and the rules, with `?task_id=` adding one task's resolution; the task
  payload carries its resolved `policy`; `foreman task override` takes
  `--triage` and `--notification` alongside the unchanged `--gate`; and
  `foreman config` prints the matrix. The dashboard grows a `triage` board
  column (shown only when work is waiting there) with an **Accept** action, the
  resolved policy in the task drawer, and a defaults-plus-rules editor in
  settings. `notification` is stamped as `notify` on
  `engine.attention_needed` and `workflow.paused`, providing the durable
  decision consumed by the following delivery slice. **No migration** —
  `status` is a text column and
  settings are JSON. Existing projects are unaffected: the two gate settings
  keep their names, defaults, and `executor_overrides.gates` shape,
  `workflow.gate_auto_approved` and the gate decision records keep their shape,
  `triage` only touches intake tasks, and `notification` only adds a payload
  field. Recorded as ADR-0014 and documented in MANUAL §14. (The task specified
  ADR-0013, which slice 5 had already taken, so this landed as ADR-0014.)
- **slice 7, durable notification delivery** (`feat/task-d5da554de317`,
  FOR-12): migration 18 adds project-scoped webhook destinations and a durable
  delivery outbox. The orchestrator turns policy-stamped attention, human-gate,
  and completion events into one idempotent row per enabled destination without
  performing network work. `foreman serve` drains bounded batches between
  passes and `foreman run` drains once before returning. Webhook POSTs use a
  versioned, self-contained JSON payload, optional static headers, and optional
  HMAC-SHA256 signing whose secret is read from a named environment variable
  rather than stored. Failures retry with exponential backoff capped at 30
  minutes; the fifth failed attempt leaves a diagnostic row and emits
  `notification.failed` without changing the source task. New `foreman notify
  add|list|remove|test|deliveries` manages and diagnoses the channel. The
  dispatcher and worker are failure-isolated from task execution. Recorded as
  ADR-0015 and covered by `tests/test_notifications.py`.
- `fix/cancelled-dependency-blocks`: only a `done` dependency satisfies a
  task's `depends_on`; a task whose dependency was cancelled is blocked with
  "Dependency cancelled: …" and an `engine.attention_needed` turn
  (`dependency_cancelled`) so a person re-plans it, instead of being started
  as if the prerequisite had shipped; `foreman task cancel` and the dashboard
  cancel refuse a task with a running run while an engine is resident.
- `fix/task-branch-refresh`: every develop visit first merges the default
  branch into the task branch when it is behind and the merge is clean
  (`engine.branch_sync`, mode `refresh`, with `commits_behind`); a refresh
  that conflicts is handed to the developer as guidance (mode
  `refresh_conflict`); an unconcluded merge left by an interrupted pass is
  never aborted (mode `merge_in_progress`); `foreman approve` and `foreman
  deny` exit 75 with an honest message when the resumed workflow pauses on a
  backend quota. New `commits_behind` and `merge_in_progress` git helpers.
- `fix/runner-quota-exhaustion`: a backend usage quota running out mid-step
  (Claude Code's "session limit" result after a rejected `rate_limit_event`)
  is a `QuotaExhaustedError` carrying the reset time; `run_with_retry`
  surfaces it once without retries; the orchestrator pauses the task at its
  current step (`in_progress`, resume point persisted, lease released, no
  loop budget spent) with `Run.failure_type=quota` and an
  `engine.quota_exhausted` event instead of blocking it; `foreman run` exits
  75 with the reset time; `foreman serve` waits for the reset (bounded to
  one minute to six hours) and resumes. `Run.failure_type` is now set for
  quota, preflight, infrastructure, and agent failures. Idle passes are
  narrated once at INFO and repeated at DEBUG.
- `fix/runner-progress-lines`: the Claude Code runner turns progress-only
  stream lines (`system`/`thinking_tokens`, allowed `rate_limit_event`) into
  non-persisted `agent.tick` heartbeats instead of one `agent.tool_use` plus
  one `agent.raw_output` row each; tool results are persisted as a capped
  `agent.tool_result` preview instead of a full-payload tool use; the session
  init line becomes a small `agent.session`; raw lines are capped at 8,000
  characters; unknown message types are kept as raw output only

### Sprint 53 — Phase 0 unattended safety

- opened sprint 53 from Phase 0 of the production readiness review
  (`docs/reviews/production-readiness-review.md`); Phases 1–2 queued in the
  backlog.
- **slice 1, store safety** (`fix/store-concurrency-safety`): migration 14
  rebuilds the gate tables with `ON DELETE` rules so run pruning and task or
  sprint deletion no longer fail on foreign keys, indexes `events(task_id,
  timestamp)`, and replaces scan-based task keys with a per-project sequence
  under a unique index; migrations apply atomically per version; file-backed
  stores use WAL with a busy timeout and retrying hot writes; deletes are
  dependent-aware; the dashboard initializes the schema once; project settings
  are validated at run start, at the dashboard settings endpoint, and at
  `foreman config --set`, with event, run, and prompt retention now explicit
  opt-in settings.
- **slice 2, runner process lifecycle** (`fix/runner-process-lifecycle`): new
  `foreman/runner/process.py` with `ManagedProcess` (pumped stdout and
  stderr, silent-tick wake-ups, own session, process-group terminate and
  kill) and shutdown handlers that stop every registered child and raise
  `EngineShutdown`; both runners rebuilt on it so time and cost gates fire
  while an agent is silent, the Codex handshake is wall-clock bounded, and
  output decodes as UTF-8 with replacement; the orchestrator heartbeats the
  lease on ticks, raises `LeaseLostError` on a refused renewal, and marks the
  run `killed` on shutdown or lease loss while leaving the task resumable;
  `foreman run` exits 130 on SIGTERM or Ctrl+C; `_builtin:run_tests` honors a
  new `test_timeout_seconds` setting and kills its process group on timeout.
- **slice 3, output contract and signals**
  (`fix/output-contract-and-signals`): the completion marker and reviewer
  verdict are read from the agent's final message only; the decision grammar
  accepts `Decision:`/`Verdict:` prefixes, ignores placeholder option lines,
  and turns multiple distinct verdicts or an undeclared verdict into an error
  that triggers the corrective retry; roles declare `[completion] outcomes`,
  `[completion] review_kind`, and `[signals] allowed`, which replace the
  engine's hardcoded reviewer ids in normalization, workflow validation, and
  completion evidence (tiered-review approvals now satisfy the merge guard);
  signals are parsed once, only outside code fences and quotes, accept
  pretty-printed JSON, are deduplicated per step, and are recorded as
  `signal.rejected` when a role may not emit them.
- **slice 4, workflow order and merge gate**
  (`fix/workflow-test-before-review`): every shipped workflow now tests
  before it reviews and ends in a `merge_approval` human gate; gate steps
  declare a `policy`, resolved from the new `merge_approval` (default
  `auto`) and `plan_approval` (default `human`) settings or a per-task
  `executor_overrides.gates` entry; an `auto` gate is approved by the engine
  with a `workflow.gate_auto_approved` event and a `policy:<name>` decision
  record; the reviewer prompt's developer summary now comes from the latest
  agent run instead of the test built-in.
- **slice 5, dashboard minimum safety** (`fix/dashboard-minimum-safety`):
  wildcard CORS removed (explicit `--allowed-origin` allowlist only); a
  shared access token (`--token` / `FOREMAN_DASHBOARD_TOKEN`) guards every
  `/api` route via bearer header, `X-Foreman-Token`, or `?token=` on the
  event stream; non-loopback binds are refused without a token unless
  `--allow-insecure-network`; the manager chat is loopback-only unless
  `--allow-remote-manager` (disabled routes answer 403); project creation
  requires an existing git repository path, optionally inside
  `FOREMAN_DASHBOARD_REPO_ROOTS`; the events page size is capped at 500;
  the frontend sends the token and prompts for it on 401.
- **slice 6, cleanup** (`chore/remove-bootstrap-supervisors`): removed the
  bootstrap supervisor scripts (`scripts/reviewed_claude.py`,
  `scripts/reviewed_codex.py`), their tests, `foreman/supervisor_state.py`,
  and the legacy `finalize_supervisor_merge` path; dropped the unused
  `anthropic` dependency; the autonomous signal contract appears in
  `.foreman/context.md` only for autonomous projects. **Sprint 53 closed**
  with 605 backend and 18 frontend tests passing; archived under
  `docs/sprints/archive/`.

### Milestone

- **Review roadmap complete (Phases 0–7).** The stacked review branches
  (Sprints 49–52) were fast-forwarded to `main` in order on 2026-06-13
  (`62c2e25` → `2ca7b49` → `b53f930` → `35b667c`) and the sprints archived under
  `docs/sprints/archive/`. Full suite: 571 tests passing.

### Frontend

- tied the React dashboard to the finished backend (see
  `docs/reviews/frontend-gap-analysis.md`): the task drawer now shows completion
  evidence (verdict / proof status / score / judged-by + per-criterion
  checklist) and the per-run model; an `engine.attention_needed` supervision
  banner runs one manager turn via `POST …/meta/supervise`; the settings panel
  binds to the real `ProjectSettings` (models/token-economy, criteria judge,
  cost/time gates, `completion_guard_enabled`) and can select
  `development_tiered`; new-task creation carries description, complexity, and
  dependencies.
- fixed frontend bugs: the new-task "Context" field was silently dropped; the
  Run/Stop toggle inferred agent state from task status instead of the
  authoritative `agent_running` field; the settings panel wrote inert keys and
  offered a Codex meta-backend option that broke the manager; the active-sprint
  header showed a dead "Stop" button when idle — it is now a Run↔Stop toggle so
  an idle sprint exposes a usable "Run".
- backend: `POST /api/sprints/{id}/tasks` (`create_task`) now accepts
  `description`, `complexity`, and `depends_on` (matching the CLI); `get_task`
  serializes `completion_evidence`.

### Task keys + dependency picker

- added Jira-style per-project task keys (`FOR-102`): migration 13
  (`projects.task_key_prefix`, `tasks.task_key`), write-once key assignment in
  `ForemanStore.save_task` with a per-project sequence, a derived prefix
  (`derive_task_key_prefix`), and a one-time backfill for existing tasks. Keys
  are surfaced in the task card, the detail drawer, the active-sprint list, and
  dependency chips, and in the `get_task` / `list_sprint_tasks` / `create_task`
  payloads.
- replaced the dependency checkbox list with a Jira/Linear-style **search-to-add
  picker**: type to filter by key or title, selected dependencies render as
  removable chips (key shown, full title on hover). Scales to large sprints and
  matches the form styling.

### Frontend UX (Tier 3 polish)

- surfaced `zero_cost_token_runs`: token totals in the sprint status bar and the
  topbar now show "cost unknown for N runs" so third-party (zero-cost) endpoints
  read honestly.
- consistency pass: unified the inline-card close control to the standard `×`
  glyph and normalized remaining lowercase copy ("Loading…").
- landing copy: replaced the dev-jargon project-overview subtitle
  ("SQLite-backed project state, active sprint summaries, and aggregate engine
  totals.") with plain language, and reframed the project-card footer's raw
  `task_selection_mode · workflow_id` (`directed · development_tiered`) through
  new `formatSelectionMode` / `formatWorkflowLabel` helpers
  (e.g. "Directed · Tiered workflow").

### Frontend layout polish

- project overview: "+ New project" is now a dashed add-tile at the end of the
  project grid instead of a header button.
- project view: the manager panel opens by default and can be resized with a
  drag handle (360–820 px); project content sits in a centered 1080 px measure;
  queue task-row status hugs the title with a middot separator; the activity
  composer uses the accent send button.

### Frontend UX (Tier 2 cont.)

- unified the three task-creation surfaces (New Task modal, New Sprint modal
  initial tasks, inline queue editor) on a shared `TaskFormFields` component so
  they no longer diverge in capability; `create_sprint` initial tasks persist
  complexity.
- meta-agent panel: paginated history with a "Load older messages" control,
  a `supervision` origin badge on engine-triggered turns, and a model-agnostic
  "Manager — Planning & supervision" header (was hardcoded "Claude Code").
- added a **Roles** topbar surface (`RolesModal`) to inspect and edit role
  model / backend / permission mode via `GET`/`PATCH /api/roles`.
- normalized status casing (sprint badges, queue task rows now Title-Cased) and
  tidied empty-state copy.

### Frontend UX (Tier 2)

- Approve/Deny are now scoped to tasks actually paused at a human gate, via a
  new backend `awaiting_human_gate` flag on the task payloads (computed from the
  task's current workflow step role); tasks blocked for other reasons
  (cost/time/loop/evidence) show an explanatory note instead of approve/deny
  buttons that wouldn't apply.
- the sprint board shows a **Cancelled** lane when the sprint has cancelled
  tasks (previously they vanished from the board).
- sprint title and goal gained visible ✎ edit buttons (previously editable only
  via an undiscoverable double-click); planned sprint cards show an expand
  chevron + "Click to expand" affordance so they're distinguishable from
  navigate-on-click active/archived cards.

### Frontend correctness & polish

- fixed the New Task form offering an invalid `bug` task type (which the backend
  rejected with a 400) and omitting `fix`/`docs`/`spike`; the chip list and the
  `getTaskTypeClass` colour map now match the backend `TASK_TYPES`.
- removed the two dead activity filters (`File changes`, `Review` matched event
  types the engine never emits); the feed now filters into Agent / Workflow /
  Decisions / Human, every bucket populated, and the new roadmap events
  (`engine.attention_needed`, `engine.completion_evidence`,
  `workflow.model_selected`, guard/gate events) get readable summaries.
- "Running" now consistently means a live agent (`agent_running`) across the
  landing cards, the topbar engine status, and the breadcrumb — resolving the
  contradiction with the Run/Stop control; the breadcrumb sprint dropdown no
  longer miscolours `cancelled`.
- relabelled the misleading "{n} awaiting approval" project badge to "{n}
  blocked"; aligned the sprint modal's task "Context" field to "Description";
  moved the evidence/supervision colours onto the theme tokens.

### Fixed

- supervision now emits the full attention-trigger taxonomy: a completion/merge
  guard block whose proof gate failed raises `engine.attention_needed` with
  trigger `evidence_failed` (vs. the generic `task_blocked`), and a sprint that
  resolves while the engine stops (supervised/directed handoff, or no further
  work) raises trigger `sprint_resolved`. Previously only `task_blocked` and
  `loop_limit` were emitted, so two triggers defined in the digest never fired.

### Documentation

- added `docs/MANUAL.md`, a complete operator's guide (install, quickstart, CLI
  reference, roles/workflows, multi-model fleet, completion evidence + proof
  gate, tiered review, meta-agent + supervision, dashboard HTTP API, settings,
  event taxonomy, troubleshooting); README now points to it.
- added `docs/reviews/review-md-backend-audit.md`, the independent backend audit
  of the `review.md` implementation.

### Added

- supervision turns and transport polish (sprint 52, review Phases 6–7):
  `foreman/digest.py` `build_attention_digest`; an `engine.attention_needed`
  event emitted exactly once when a task transitions to blocked (loop-limit and
  signal-blocker paths tagged with their trigger); a
  `POST /api/projects/{id}/meta/supervise` endpoint that runs one
  `origin="supervision"` meta turn from the digest, gating mutation on
  `autonomy_level` and rejecting replayed events with 409;
  `ForemanStore.data_version()` with `data_version`-gated SSE and `foreman
  watch` polling (interval lowered to 0.25s); persisted `Run.retry_count` from
  `agent.infra_error` events; the token-economy project settings registered in
  `ProjectSettings`; and ADR-0010
- token-economy evidence and tiered review (sprint 51, review Phases 4–5):
  `foreman/judge.py` with the keyword heuristic as the single owner plus an
  opt-in cheap-model criteria judge (direct Anthropic-compatible HTTP call,
  head/tail diff truncation, heuristic fallback on any error);
  `CompletionEvidence.judged_by` surfaced in the `engine.completion_evidence`
  event; the new `escalate` reviewer outcome; `triage_reviewer` and
  `frontier_reviewer` roles; a `{completion_diff}` curated-diff prompt payload
  for decision roles (`review_diff_max_chars` setting); and the
  `development_tiered` workflow (develop → triage → escalate-to-frontier review)
- per-task executor overrides and a model-escalation ladder (sprint 50, review
  Phase 3): migration 12 (`executor_overrides_json`, `complexity` on tasks);
  `Task.executor_overrides`/`Task.complexity`; role `[agent] model_ladder`;
  the pure `resolve_step_model` model-resolution function wired into the
  workflow loop and native runner with a `workflow.model_selected` event per
  agent step; architect `complexity` persisted from `signal.task_created`;
  `foreman task add --complexity`; `foreman task override` CLI; and
  `executor_overrides` on the dashboard `PATCH /api/tasks/{id}` plus task
  payloads
- durable, store-backed meta-agent chat (sprint 49, review Phase 2): migration
  11 (`meta_sessions`, `meta_turns`); store methods for session/turn
  persistence and cursor paging; a compact `build_state_header()` snapshot
  rebuilt every turn; a first-turn operating contract; crash-safe assistant-turn
  persistence; a configurable `meta_agent_model` setting; `limit`/`before`/
  `has_more` paging on the meta history endpoint
- `foreman task add --description`, `--sprint SPRINT_ID`, and `--depends-on`
  (validated against tasks in the same project)
- Foreman-specific repo instructions in `AGENTS.md`
- active sprint and backlog docs for the first Foreman implementation slice
- repository templates for PR summaries, checkpoints, and sprint archives
- `pyproject.toml` and the initial `foreman/` package scaffold
- a runnable CLI shell covering the spec-aligned command surface
- typed SQLite models and a spec-shaped `foreman.store` persistence layer for
  projects, sprints, tasks, runs, and events
- shipped declarative `roles/*.toml` and `workflows/*.toml` defaults
- a persisted orchestrator loop plus explicit built-in execution seams
- repo-local `.foreman.db` discovery with explicit `--db` override support
- FastAPI, uvicorn, and HTTP client dependencies for the dashboard backend
- a dedicated React and Vite dashboard frontend workspace in `frontend/`
- `foreman init` defaulting to `<repo>/.foreman.db` for repo scaffold
  generation and persisted project initialization
- runtime context projection in `.foreman/context.md` and `.foreman/status.md`
- persisted human-gate approve and deny commands
- native Claude Code and Codex runners in `foreman/runner/`
- store-backed monitoring commands in `foreman.cli` for `board`, `history`,
  `cost`, and `watch`
- `docs/adr/ADR-0001-runner-session-backend-contract.md`
- `docs/adr/ADR-0002-dashboard-data-access-boundary.md`
- `foreman/dashboard.py` with dashboard HTML shell and direct JSON endpoints
- dashboard task detail, activity feed, human message input, activity filter,
  project switcher, and approve or deny actions
- a dedicated dashboard sprint event stream for incremental live activity
  updates
- native runner task-lease heartbeats during streamed Claude/Codex execution
- `foreman/executor.py` and `tests/test_executor.py`
- end-to-end runtime coverage for the opt-in `development_secure` workflow
  plus secure workflow initialization coverage in the CLI
- explicit native backend preflight validation for Claude Code and Codex
- spec-aligned event-retention pruning for old project events
- live-tail `foreman watch` support across project, sprint, and run scopes
- `docs/adr/ADR-0003-web-ui-api-boundary.md`
- `docs/adr/ADR-0004-dashboard-backend-framework.md`
- `docs/adr/ADR-0009-multi-model-endpoints-via-role-env.md`
- per-role `[agent.env]` resolution for native runner environment injection
- `roles/developer_worker.toml` as the sequential worker-model role example
- production-hardening audit and detour planning docs
- `foreman/dashboard_service.py` as the extracted dashboard service layer
- `foreman/dashboard_backend.py` as the FastAPI dashboard transport
- `scripts/dashboard_dev.py` as the combined local dashboard frontend and
  backend launcher
- `frontend/src/App.test.jsx` and the frontend bundle build validation path
- dashboard transition checkpoint notes while the embedded shell was being
  replaced
- `docs/checkpoints/react-dashboard-foundation.md`

### Removed

- obsolete `foreman/executor.py` and `tests/test_executor.py`; the orchestrator
  native runner path is the maintained execution surface

### Changed

- repurposed the transplanted project-memory docs from Apparatus to Foreman
- aligned the autonomous wrapper scripts and repo validation expectations with
  `docs/specs/engine-design-v3.md` and
  `docs/mockups/foreman-mockup-v6.html`
- completed `sprint-01-foundation`, `sprint-02-orchestrator`,
  `sprint-03-scaffold`, and `sprint-04-context-projection`
- completed `sprint-05-human-gates`, `sprint-06-claude-runner`, and
  `sprint-07-codex-runner`
- completed `sprint-08-monitoring-cli`, archived it, and advanced project
  memory to the runner session and backend ADR sprint
- completed `sprint-09-runner-session-backend-adr`, archived it, and advanced
  project memory to the dashboard implementation sprint
- completed `sprint-10-dashboard-implementation`, archived it, and advanced
  project memory to the multi-project dashboard polish sprint
- completed `sprint-11-multi-project-dashboard-polish`, archived it, and
  advanced project memory to the dashboard approve or deny integration sprint
- completed `sprint-12-dashboard-approve-deny-integration`, archived it, and
  advanced project memory to the persistent-session reload sprint
- completed `sprint-13-persistent-session-reload`, archived it, and advanced
  project memory to the dashboard streaming transport sprint
- completed `sprint-14-dashboard-streaming-transport`, archived it, and
  advanced project memory to the engine DB discovery sprint
- completed `sprint-15-engine-db-discovery`, archived it, and advanced project
  memory to the security review workflow sprint
- completed `sprint-16-security-review-workflow`, archived it, and advanced
  project memory to the native backend preflight sprint
- completed `sprint-17-native-backend-preflight-checks`, archived it, and
  advanced project memory to the event-retention pruning sprint
- completed `sprint-18-event-retention-pruning`, archived it, and advanced
  project memory to the watch live-tail alignment sprint
- completed `sprint-19-watch-live-tail-alignment`, archived it, and advanced
  project memory to the migration framework bootstrap sprint
- tightened repo instructions so bootstrap status no longer permits
  prototype-grade implementation decisions
- replanned the next work as a production-hardening detour covering dashboard
  API extraction, React frontend replacement, stub removal, and delayed
  migration work
- completed `sprint-21-dashboard-api-extraction`, archived it, and advanced
  project memory to the dashboard backend foundation sprint
- extracted dashboard reads, actions, and incremental stream payload assembly
  into `foreman/dashboard_api.py` while keeping the current shell functional
- completed `sprint-22-dashboard-backend-foundation`, archived it, and
  advanced project memory to the React dashboard foundation sprint
- replaced the raw dashboard stdlib server with a uvicorn-backed FastAPI
  backend while preserving the current shell and route surface
- completed `sprint-23-react-dashboard-foundation`, archived it, and advanced
  project memory to the product-surface hardening sprint
- replaced the embedded dashboard shell with a dedicated React frontend,
  built asset delivery, and frontend-aware dashboard validation
- pruned redundant dashboard transition checkpoint and PR-summary files now
  that sprint archives and the dedicated frontend checkpoint are the durable
  history
- renamed the dashboard runtime wrapper to `foreman/dashboard_runtime.py` and
  the extracted dashboard service layer to `foreman/dashboard_service.py`
- added frontend-dev support to `foreman dashboard`, Vite `/api` proxying for
  `npm --prefix frontend run dev`, and a one-command
  `npm --prefix frontend run dev:full` workflow
- removed the remaining `handle_stub` product-surface fallbacks by
  implementing the shipped `project`, `sprint`, `task`, `run`, and `config`
  CLI behaviors with direct store or orchestrator integration
- expanded CLI subprocess coverage around sprint activation and completion,
  task lifecycle operations, project inspection, config updates, and direct
  run invocation
- reconciled the loose feature and recovery branches into an integrated
  mainline candidate and restored missing repo-memory artifacts from the
  runner-session ADR branch
- closed the most visible product-surface gaps: settings panel, sprint
  creation, and task creation now run end-to-end from React components
  through FastAPI endpoints to SQLite persistence
- added 15 integration tests covering settings read/update validation, sprint
  creation, and task creation through both the service layer and FastAPI
  transport
- introduced an explicit schema migration framework in `foreman/migrations.py`
  and `foreman/store.py`: version-tracked migrations replace the old bootstrap
  DDL, `initialize()` now upgrades existing databases to the latest schema
  version automatically
- added `docs/adr/ADR-0005-schema-migration-strategy.md` documenting the
  append-only migration list, `schema_migrations` tracking table, and
  `ForemanStore.migrate()` / `schema_version()` API
- added `tests/test_migrations.py` with 17 tests covering migration list
  integrity, fresh install, idempotency on both in-memory and file databases,
  incremental upgrade from a partially-migrated store, and schema version
  accuracy
- added migration 2 (`idx_runs_project_completed`) enabling efficient run
  retention queries; `test_partial_db_upgraded_to_latest` now passes
- added `ForemanStore.prune_old_runs()` to hard-delete terminal runs and their
  cascaded events older than a cutoff while protecting blocked/in-progress tasks
- added `ForemanStore.strip_old_run_prompts()` to null out `prompt_text` on old
  terminal runs while preserving run records and telemetry
- expanded orchestrator startup pruning via `prune_old_history()` reading
  `run_retention_days` and `prompt_retention_days` project settings; emits
  `engine.run_pruned` and `engine.prompt_stripped` lifecycle events
- added `tests/test_run_retention.py` with 19 tests covering deletion,
  active-work protection, cascade event removal, and prompt stripping
- hardened active-run crash recovery so stale task leases are force-expired
  when a run is recovered and live holders are identified by recent lease
  heartbeats
- added browser-driven E2E dashboard validation via Playwright and Chromium:
  `tests/test_e2e.py` with 20 tests covering dashboard load, project and sprint
  navigation, task detail drawer, settings panel, sprint creation, and task
  creation end to end against a live FastAPI server and seeded SQLite database
- added `playwright` and `pytest-playwright` to `pyproject.toml` as optional
  `e2e` dependencies
- implemented `task_selection_mode="autonomous"` in `ForemanOrchestrator`:
  `select_next_task()` now dispatches to `_select_next_task_autonomous()` for
  autonomous projects; resumes in-progress tasks, then creates placeholder tasks
  up to the per-sprint `max_autonomous_tasks` limit (default 5)
- added 8 tests in `AutonomousTaskSelectionTests` covering placeholder creation,
  in-progress resume, no-sprint, limit enforcement, human-task exclusion,
  directed-mode unchanged, and unknown-mode error
- added `foreman db version` — shows current schema version; handles missing
  `schema_migrations` table on pre-migration-framework databases
- added `foreman db migrate` — applies pending schema migrations via
  `store.initialize()` and reports each applied version with description
- changed `ForemanStore.initialize()` to return `list[int]` (backward-compatible)
- added 7 tests in `DbCommandTests`
- completed `sprint-30-wire-dead-surfaces`: wired Stop agent button to
  `POST /api/projects/{id}/agent/stop`; added `PATCH /api/sprints/{id}` for
  lifecycle transitions (planned→active, active→completed/cancelled) with
  `started_at`/`completed_at` timestamps; added `PATCH /api/tasks/{id}` for
  `description` and `priority` updates; extended `get_task` run serialization;
  added sprint status badge and Start/Complete buttons in sprint view header;
  10 tests in `DashboardSprintLifecycleTests`
- completed `sprint-31-backlog-items`: sprint creation with inline initial tasks
  via `initial_tasks` in API body; task cancellation (`POST /api/tasks/{id}/cancel`,
  Cancel task button in drawer); task dependency display in drawer via
  `depends_on_task_ids`; event log load-more with `before_event_id` cursor and
  `has_more` flag; cancelled sprint filter in list and kanban Done column;
  8 tests in `DashboardSprintTaskBacklogTests`
- completed `sprint-32-tier1-editing`: task field editing in `TaskDetailDrawer`
  (title, type, acceptance criteria) via edit mode with chip selector and
  textarea; sprint goal inline editing in sprint header via `update_sprint_fields`;
  activity panel auto-scroll using `useLayoutEffect` and scroll-position tracking;
  `containerRef`/`onScroll` props on `EventList`; 11 tests in
  `DashboardTaskEditingTests`
- completed `sprint-33-tier2-gaps`: `workflow_current_step` added to
  `list_sprint_tasks` response and shown as badge on in-progress task cards and
  in detail drawer; project creation from dashboard via `POST /api/projects` and
  `NewProjectModal`; `foreman run` from dashboard via
  `POST /api/projects/{id}/agent/start` spawning a `foreman run` subprocess with
  double-start prevention; Run ▶ / Stop ■ toggle in sprint header; 9 tests in
  `DashboardTier2Tests`
- completed `sprint-34-task-edit-enforcement`: `update_task_fields` now tracks
  which fields actually changed; emits `human.task_edited` event with
  `changed_fields` payload for `in_progress` and `blocked` tasks; creates a
  synthetic dashboard/edit run if no run history exists (FK safety);
  `getEventCategory` broadened from exact `human.message` match to `human.*`
  prefix; `formatEventSummary` handles `human.task_edited`; 6 tests in
  `DashboardTaskEditEventTests`
- completed `sprint-35-dashboard-crud-polish`: fixed board-view filter leak
  (status filter buttons and sort conditioned on list view mode); added
  `ForemanStore.delete_task()` and `delete_sprint()` with FK-safe cascade
  (events → runs → tasks → sprint); `DELETE /api/tasks/{id}` and
  `DELETE /api/sprints/{id}` routes; delete buttons in `TaskDetailDrawer` and
  on sprint cards with confirm guard; sprint title inline editing in sprint
  header; `order_index`, `started_at`, `completed_at` added to all sprint API
  responses; `order_index` editable via `PATCH /api/sprints/{id}`; ↑/↓ reorder
  buttons on sprint cards swap adjacent `order_index` values; sprint list sort
  fixed to use `order_index` (was using undefined `order` field); `formatDate`
  added; dates shown on sprint cards and in sprint header stats; 18 new tests
  across `DashboardDeleteTests` and `DashboardSprintOrderTests`; 95 dashboard
  tests and 20 E2E tests all passing
- completed `sprint-36-intervention-and-ordering`: sprint list ordering fixed
  (active/completed above planned); `POST /api/tasks/{id}/stop` route for
  stopping individual in-progress tasks; Stop button on task cards and in
  task detail drawer; Cancel sprint button in sprint view header for active
  and planned sprints; board column equal-width fix (`minmax(0, 1fr)`);
  custom scrollbar styling; duplicate branch name generation fixed in
  orchestrator; 6 new tests in `DashboardInterventionTests`; 95 dashboard
  tests passing
