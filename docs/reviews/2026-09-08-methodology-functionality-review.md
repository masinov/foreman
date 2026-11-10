# Foreman: independent methodology and product experience review

> Saved in the repository at the user’s request. The observations and read-only
> review notes below describe the original review sessions on 2026-09-08,
> not subsequent implementation or this archival step. Screenshots are
> preserved alongside the reviews; live state changed between captures.

Reviewed 2026-09-08. Repository snapshot: detached HEAD `951514f`. Live UI: local dashboard on port 8091, with FOR-9 (policy matrix v2) running. This review assesses the checked-out implementation and currently served product; it does not assess the unfinished changes in the running task's worktree.

Read-only review. No repository files, branches, settings, tasks, or engine commands changed. Browser interception blocked non-GET API calls. Screenshots and this report live in `/tmp`.

## Assessment

Foreman has a credible engineering foundation and a recognizable visual identity. Its principal weakness is the relationship between delivery, evidence, and human control. The engine produces many records of work; the interface makes a person reconstruct what those records mean. The development process can accept a working API/component seam without establishing that a person can use the resulting capability.

SQLite state, declarative roles/workflows, separate React/API boundaries, independent review sessions, worktree isolation, and the test-before-review sequence are strengths worth preserving. The current sprint's use of real engine runs to discover failures is also useful. The issues below do not call for replacing those foundations.

## 1. High: guidance promises delivery that the implementation does not establish

`frontend/src/App.jsx:1070` presents a task-targeted guidance composer. `foreman/dashboard_service.py:1381` saves a `human.message` event and returns `status: sent`. Searching the Python source finds that event name at the producer, with no corresponding runner/orchestrator consumer. The context builder reads tasks, sprints, and carried feedback, rather than this message stream.

A person can reasonably believe the active developer received their correction. The system establishes only that a message was recorded. This is a product contract failure, independently of whether a person can reach the composer.

Required outcome: distinguish recorded, queued for a particular run/turn, delivered, and acknowledged. Delivery must be tested against agent input. If the capability is only an annotation, its label and response must say so.

## 2. High: the drawer prevents use of the guidance composer

Reproduced at 1440×1000. Selecting FOR-9 enables the guidance textarea and simultaneously opens a fixed 520px drawer over the right-hand activity panel. A browser hit test at the textarea's center hits the drawer's description instead. Closing the drawer clears `selectedTaskId`, which disables guidance again.

Sources: `frontend/src/styles.css:2302`; `frontend/src/App.jsx:1100`; `frontend/src/components.jsx:1102`.

Evidence: [foreman-review-detail.png](assets/2026-09-08-ui-review/foreman-review-detail.png). Move task guidance into the task surface, or separate task targeting from drawer visibility. Selection, inspection, and communication need compatible layouts.

## 3. High: completion evidence overstates what has been verified

`foreman/judge.py:35` uses word overlap against agent output or filenames. `heuristic_checklist` translates sufficient overlap into `status: passed`. `frontend/src/components.jsx:1022` displays checkmarks, a numeric score, a verdict, and `proof: passed` where supplied. The heuristic label is visible, but does not repair the stronger semantics of “passed” and “proof.”

A direct, read-only probe passed the criterion “The dashboard supports keyboard navigation and displays actionable error messages” when the only evidence was `not implemented:` followed by the criterion, with no changed files. This probe establishes a false positive in criterion evaluation, not that the entire merge guard can be bypassed by that input alone.

`foreman/orchestrator.py:1102` also awards score for changed-file count and diff context lines. These measure change volume, not product quality. Tests and reviewer approval remain additional gates; they do not make this numerical score a measure of correctness.

Required outcome: report facts with provenance—test result, reviewed commit, reviewer decision, criterion evidence, and unverified claims. Reserve “verified” for the check actually performed. The backlog already proposes dropping the numeric ladder; this should be treated as a trust issue, not cosmetic cleanup.

## 4. High: the validation method misses actual user journeys

`frontend/src/App.test.jsx:274` tests guidance by selecting a task, locating the textarea, dispatching change/click events, and asserting a mocked service call. The test does not exercise browser hit testing or agent delivery. It therefore cannot detect either finding 1 or 2.

The standard workflow has developer → tests → code review → merge gate → merge → done. The reviewer prompt asks whether tests exist and are plausible, checks implementation and docs, and has no required rendered-product evidence. `docs/TESTING.md` allows “browser or bundle-level validation”; a successful bundle cannot demonstrate usable interaction.

This is the methodological explanation for the defects: local seam success substitutes for end-to-end acceptance. Add a small browser acceptance pack for critical operator journeys and require rendered evidence for changed UI states. Good initial journeys: inspect running task and send guidance; review a blocked merge; pause and confirm effect; recover from an engine failure. Keep the existing engineering tests.

## 5. High: responsive behavior is broken, beyond a density preference

At 1100px the live sprint body computes to `700px 400px`. At 390px it computes to `33px 400px`, leaving the board unusable and activity clipped. The media rule for `.sprint-body` loses to the more specific `.sprint-body.with-activity`; project manager layout also carries an inline grid width that requires deliberate responsive handling.

Sources: `frontend/src/styles.css:1679`, `:3894`, `:3924`; `frontend/src/components.jsx:728`.

Evidence: [foreman-review-1100.png](assets/2026-09-08-ui-review/foreman-review-1100.png), [foreman-review-mobile.png](assets/2026-09-08-ui-review/foreman-review-mobile.png). Adopt explicit compact layouts with board/activity/task tabs or full-page detail. Validate with activity open, drawer open, and long real task titles—not only empty or short fixtures.

## 6. Medium-high: the information hierarchy favors telemetry over supervision

The live project page devotes 540 of 1440 pixels to an empty Manager panel. Worktree paths and Prune are near the project heading. The active task is one line among struck-through completed tasks and cancelled tasks. Entering the sprint opens four equal columns, including empty Todo and Blocked columns, while Done contains a long stack.

The live activity panel repeats long task titles and machine event names. `agent.raw_output` and `agent.tool_result` rows often display only their type again; a full shell script can dominate the feed. A selectable Agent filter helps, but the default still asks users to sift telemetry.

Sources: `frontend/src/components.jsx:334`, `:414`, `:931`, `:985`; `frontend/src/App.jsx:980`.

Evidence: [foreman-review-project.png](assets/2026-09-08-ui-review/foreman-review-project.png), [foreman-review-sprint.png](assets/2026-09-08-ui-review/foreman-review-sprint.png).

An operator's first screen should answer: What is running? What changed recently? Is it healthy? What needs my decision? What happens next? Put diagnostic paths and raw events one level deeper. Keep the kanban as a view, but provide a compact operational list or current-work summary. Manager chat should complement direct controls and evidence.

## 7. Medium-high: task details are a record dump, not a review workspace

The current FOR-9 description fills essentially the whole first drawer viewport. It is rendered as an unstructured text block, with literal Markdown syntax and dense implementation prose. Details, acceptance criteria, evidence, blocker, gate actions, and run history follow below it. Run rows show role, step, model, duration, run status, and tokens; they do not present the actual reviewer decision rationale or a navigable diff in this component.

Source: `frontend/src/components.jsx:1102`. Evidence: [foreman-review-detail.png](assets/2026-09-08-ui-review/foreman-review-detail.png).

Use a short task summary, current state and next action at the top. Separate Overview, Changes, Checks, and Activity. Render descriptions as structured content. Approval should name the effect—such as merging a particular reviewed commit into main—and bring the relevant evidence next to that decision. Raw machine identifiers and full task instructions remain accessible as secondary details.

## 8. Medium: the aesthetic identity is stronger than its legibility

Charcoal surfaces, warm gold, serif headings, and restrained borders give Foreman a coherent identity. Preserve that direction. The problem is the repeated use of tiny monospace text and low contrast for information people must read.

The tertiary color `#5a5a5e` has a calculated contrast of 2.85:1 against `#0c0c0e` and 2.52:1 against cards `#1a1a1f`. It appears widely in 9–11px labels and metadata. Completed tasks are additionally dimmed and struck through. Long names wrap across many lines in narrow cards; headings and goals truncate. The page can look sparse and still feel difficult to scan because useful content occupies narrow, faint areas.

Source: `frontend/src/styles.css:1` and typography rules throughout. Screenshots above show the actual result.

Use a more readable body scale and stronger secondary text, reserve monospace for identifiers and logs, reduce repeated metadata, and distinguish completed work without rendering its history illegible. A restrained dark interface can still have clear hierarchy.

## 9. Medium-high: durable memory contains conflicting current instructions

`docs/STATUS.md` is 1139 lines and includes duplicate Current implementation branch / Active branches sections with incompatible next actions. Its opening says worktrees now have isolated environments; a later update says this repo requires linking the operator venv. `docs/TESTING.md` still gives the shared-venv configuration. The backlog parking lot still asks to persist manager sessions, although the same backlog describes that work as completed in sprint 49. The spec still lists some already-built capabilities as future work.

This matters because agents are explicitly required to read these files as durable truth. They must infer which statements are current before they can execute safely. The repository scaffold validator passed during this review, so its success does not establish semantic consistency.

Make STATUS a compact current snapshot. Move chronological updates into archives; retain one current environment recipe; mark superseded ADR/spec passages through an explicit applicability index if the authoritative artifacts are not being revised. Generate appropriate runtime summaries from SQLite rather than maintaining parallel, competing task status lists.

## 10. Medium: asynchronous state and save behavior undermine confidence

`refreshProjectScope`, `refreshSprintScope`, and `refreshTaskDetail` set state inside the request helpers. The effect cancellation flags protect later error handling, not those successful writes. Rapid navigation can therefore allow an older request to overwrite the new selection's data. This is established by code inspection; I did not induce a live race against the running task.

`SettingsPanel.handleSave` calls the asynchronous update and immediately clears its draft without waiting for success. The task drawer keeps edit drafts independent of the selected task ID. These are instances where the interface needs an explicit pending/success/failure and entity-identity contract.

Sources: `frontend/src/App.jsx:188`; `frontend/src/components.jsx:1102`, `:1442`.

Guard requests by selected entity or abort them; retain drafts on failed saves; reset or explicitly preserve drafts when switching entity. Browser coverage should include delayed responses and failed mutations against fixtures.

## Recommended sequence

1. Ship one coherent “inspect and steer a running task” slice: reachable composer, explicit delivery semantics, visible acknowledgement, browser and runner integration checks.
2. Build a decision-oriented task detail surface and facts-based completion evidence.
3. Repair responsive layouts and typography, then simplify operational hierarchy using real sprint data.
4. Make current-state memory unambiguous and add critical browser journeys to the UI definition of done.

The central product acceptance exercise: can someone who did not build Foreman observe an active task, understand its progress, correct its direction, and decide whether to accept the result without consulting source code or a terminal?

## Validation and limits

- Read spec/mockup, status/sprint/backlog, relevant ADRs, UI, workflow, reviewer, context, evidence, and validation code.
- Read the live project overview and inspected live project/sprint/task screens at 1440×1000, 1100×800, and 390×844.
- Blocked all non-GET browser API requests; did not send guidance, approve, pause, cancel, or alter the active task.
- Browser hit test confirmed drawer occlusion of guidance. Computed styles confirmed responsive grid defects.
- Direct heuristic probe confirmed a criterion false positive. Calculated palette contrast locally.
- `./venv/bin/python -B scripts/validate_repo_memory.py`: passed.
- Full suites, rebuilds, and mutation tests were deliberately not run against the shared live environment. This is not a full security, accessibility, or backend correctness audit.
- Repository files/documentation changed: none. Branch created: none; checkout stayed detached at `951514f`. Suggested next task: item 1 above.


## Preserved screenshots

- [foreman-review-1100.png](assets/2026-09-08-ui-review/foreman-review-1100.png)
- [foreman-review-detail.png](assets/2026-09-08-ui-review/foreman-review-detail.png)
- [foreman-review-mobile.png](assets/2026-09-08-ui-review/foreman-review-mobile.png)
- [foreman-review-project.png](assets/2026-09-08-ui-review/foreman-review-project.png)
- [foreman-review-sprint.png](assets/2026-09-08-ui-review/foreman-review-sprint.png)
