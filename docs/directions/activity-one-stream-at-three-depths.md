# Activity, one stream at three depths

- Date: owner, 2026-11-21
- Moved from the hand-written `docs/sprints/backlog.md` on 2026-11-26 (FOR-70). The words below are as they were written; only a reference to another section is now a link.

Built in three slices the same day, then redesigned after the owner's
review: rows of two and three lines, too much for a summary, titles full on
one page and cut on another, and a project list that mixed sprints, tasks
and the engine ("I want you to notice these things by yourself"). The
design that replaced it (`feat/activity-one-row`):

- **One row shape for every activity list**
  (`frontend/src/pages/shared/ActivityTable.jsx`): When · (Project) ·
  Subject · What happened · By · (numbers). One line per row, the same
  column widths on every page; the subject (key, then title) is cut with
  "…" at the same width everywhere, all of it on hover; why (a reviewer's
  reason, a failure, a person's reason) is on hover and on the page the
  row leads to, never under the row. At phone width the project, who and
  the numbers give way; what happened stays.
- **Each level lists its own things:** workspace Recent and project
  Activity, sprints (planned, started, finished) and the engine (stopped,
  paused, resumed, died); sprint Activity, each task's development, tests,
  review, a person's decision, merge, block, close or cancel, with a
  Problems filter (`GET /sprints/{id}/activity`); task Activity, every run,
  with the reason above the picked run's output. A sprint-level phrase
  names its step ("Tests passed", "Sent back", "Merged"), so there is no
  step column.
- **Left out:** bookkeeping runs, gates decided by the project setting, a
  running engine (the engine row says it), a merge's numbers (the outcome
  line says how the work went).
- **Everywhere:** "Activity" as the title, "Earlier" for more, day and time,
  lists that read again while the page is open (`usePagedList` follows the
  page's refresh), and the outcome line as one short sentence.
- **After the owner's second look (same day):** the engine's every state
  change is listed, starts included, so a stop never follows a stop (the
  owner: the rule must be solid, not special to some stops); the sprint's
  Activity has a Key column, as its task list does, and the project's a
  sprint-name column; the headings no longer repeat the tab ("Sprints and
  engine", "Runs"); "user", not "person", wherever the page or the CLI
  names someone (owner).
- **Not done:** a user's name on a decision at a gate, or on an engine
  stopped by a signal (neither records who; stage 2 identity will).
