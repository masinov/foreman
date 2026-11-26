# Conflicts between the spec, the design and the code

When the spec (`docs/specs/engine-design-v3.md`), the design
(`docs/design/dashboard-v7/`) and the code disagree, trust the spec for system
behaviour and the design for UI structure, wording and look (ADR-0020), and
record the conflict **here**, before changing behaviour, one bullet each with
the date, who decided and the ADR if there is one. This file was the
'Documented conflicts' section of `docs/STATUS.md` until 2026-11-26, when
Foreman began writing that file from its database; the entries are as they
were then.

- Spec 6.4 (a finished sprint is tagged, with a note where asked) was
  half built until sprint 62, slice 2 (ADR-0036). What the spec leaves open
  is decided there:
  - a taken tag name gets `-2`;
  - the tag is pushed where merges are;
  - a failure leaves the sprint finished and says why.

- Spec 6.3 says an *autonomous* project has its sprints finished by the
  engine. Since 2026-11-19 (owner) that is the project setting
  `sprint_completion` ("Finish sprints: A user / Foreman"); the autonomy
  level no longer decides it (ADR-0025 amendment).

- Design v7 draws every board column open, and an empty one says "None". On
  the dashboard a column folds to a narrow strip showing its name, read
  downwards, and its count; the count is gold when a task in it needs you.
  An empty column starts folded, and a person's own fold or open is
  remembered per project in their browser (owner, 2026-11-18: a long workflow
  made the board unreadable). The design's open columns share the row's
  width; on the dashboard every open column is 272px wide, as Trello's lists
  are, and the board scrolls sideways past the page (owner, 2026-11-18).
  The board is 160px taller than the room left in the window below where it
  starts (owner's choice in the board lab, 2026-11-18). A column with more
  cards scrolls them under its heading, and an edge where columns are cut
  off fades out. The design draws the board growing with its tallest column.
  Each column is a panel, with its cards one step lighter
  (`--color-panel-item`). The drawings show no column panels; the design
  README's rule for panels was revised to include them (below). A column's
  scrollbar sits in the panel's margin.
- The design README's "Look" was revised by the owner on 2026-11-18. A
  tinted panel now holds a group of things one may act on: Needs you, the
  decision, a board column, a manager's proposal. Before, the tinted
  surface meant "act here", and only Needs you and the decision had it.
  The proposal card lost its outline and is a panel. The manager side bar
  has the page's ground instead of the bar tone, so a panel in it shows. Every scrollbar in the
  app, the page's own included, is thin and grey. The drawings were not
  redrawn: they show the outlined proposal card and the browser's
  scrollbars. This is the same feature as Jira's open request
  JRACLOUD-85706, and Trello, YouTrack and Linear have it.
- Design v7 keeps gold for "needs you" and the primary decision. Controls
  that open more in place ("Show all", "More details", "Finished sprints",
  "Earlier") are gold too since 2026-11-17 (owner: one look for all of
  them, grey or gold; gold chosen because text is in both greys). One
  token, `--color-expander`, sets it.
- Design v7 draws Edit and More beside a task's title, and in "Needs you"
  a button only on approve-merge rows, with the fourth kind named
  "unblock". Since ADR-0030 (owner, 2026-11-17) the title also has the
  state's button (Run next, Stop or Reopen) and Close, More holds only
  Block, Split and Delete, and a blocked task's row reads "Blocked", says
  why, and has Unblock.
- Design v7 draws the line between "Needs you" rows stopping short of the
  tinted surface's edges. The dashboard runs it edge to edge, like every
  other list (owner, 2026-11-17).
- Design v7's `05-task-overview.html` shows the manager's side bar on a
  task page. Since ADR-0029 (owner, 2026-11-17) the side bar on a task is
  the conversation with the task's agents; the screen is not redrawn.
- Shipped workflows test before review and gate the merge behind a
  policy-governed human gate; spec §5 shows review first.
- `_builtin:mark_done` terminates a workflow with no outbound transition.
- Events require a run and a task, so project-level events attach to a
  synthetic system run on one project task.
- Spec §6.2 says that in autonomous mode the orchestrator does not create a
  branch and the agent reports its own. The engine creates the branch and
  worktree in both modes (ADR-0012, amended 2026-11-11); the agent names the
  task, not the place it works in.
- Spec §6.3 revised 2026-11-16 (ADR-0025): the engine completes a resolved
  sprint only in an autonomous project; in a directed or supervised one the
  sprint stays active until a person finishes it. Implemented in
  `SprintFlow.resolve`; `engine.sprint_ready` now means "resolved, waiting for
  a person".
- Spec §6.4 sprint checkpoints (tag, note, event) were not built when this was written; they were built in sprint 62, slice 2 (ADR-0036; the first entry above).
- ADR-0007 described a restricted planner session that was never built; the
  manager chat was a full-access Claude Code session that changed project
  state itself, against the design's "it proposes changes; nothing happens
  until the person confirms". ADR-0022 (2026-11-13) supersedes ADR-0007: the
  manager proposes (`foreman proposal create`), a person confirms in the side
  bar or with `foreman proposal confirm`, and the CLI refuses every other
  state change inside a manager session. The session still has a shell, so
  this is enforced at the CLI boundary, not sandboxed.
- `AGENTS.md` named `docs/mockups/foreman-mockup-v6.html` as the UI
  authority. On 2026-11-12 the owner agreed a new design and said it was
  ready for implementation; `docs/design/dashboard-v7/` is now the UI
  reference (ADR-0020) and the mockup is kept as history. The old application
  was removed on 2026-11-12 by owner decision (ADR-0020, decision 11);
  `/dashboard/legacy` is not found.
  `docs/design/dashboard-v7/legacy-capabilities.md` lists what it could do
  and where each thing is now.
- The running dashboard differs from the design's drawings where the owner
  corrected it on 2026-11-13 (ADR-0020, Amendments): the backlog is a page of
  its own, reached from a button beside Project settings, not a third tab;
  the breadcrumb has no "Workspace" step; planned sprints are reordered with
  earlier and later buttons, not by dragging. The design README states the
  first of these; the drawings were not redrawn.
- The design's Needs you has four kinds: accept filed work, approve a plan,
  approve a merge, unblock. Pending decision gates (a proposed sprint order)
  are a fifth kind the design does not show. Resolved: the needs-you endpoint
  carries them as `settle_order`, so they appear in Needs you on the
  workspace and project pages ("Settle sprint order", with Accept and
  Reject), settled with `PATCH /api/v1/gates/{id}`. The design README still
  names four kinds; revise it when product direction is next edited.
- Resolved (sprint 58 slice 3, ADR-0021): the design's backlog is a sprint
  row of kind `backlog` that is never listed or run as a sprint; the standing
  "Intake queue" sprint is gone (migration 21 moved its waiting work into the
  backlog). Accepted intake work and agent follow-ups now wait there until a
  person plans them into a sprint, on the backlog page.
- Spec 5 and 7 describe `write_pr_summaries` (completion summaries written to
  `docs/prs/` by the merge step). It was never built in the engine, and
  ADR-0040 (sprint 65, 2026-11-26) retires `docs/prs/`: a task's own record
  holds what a PR note held, and the merge commit's message carries the task's
  key, title and change file text. The setting is no longer in a new project's
  defaults; the spec was not revised.
- ADR-0040 section 2 (sprint 65): `docs/STATUS.md`, `docs/sprints/current.md`
  and a finished sprint's archive file are generated by Foreman from its
  database (project setting `generate_copies`). Spec 6.4 lists the
  checkpoint's note and tag only; the copies are written in the same commit.
