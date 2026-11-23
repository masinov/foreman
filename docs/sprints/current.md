# Current Sprint

## Sprint 62 — finish what's there

- **Opened:** 2026-11-23 (owner: "Go", on the list drawn from the backlog
  after it was checked against the code).
- **Status:** in_progress
- **Method:** by hand, one slice at a time. A slice that changes what a page
  shows starts from a mockup where it is more than wording.

### Goal

The product that exists holds together before stage 2 of `docs/ROADMAP.md`
(the manager and people) starts:
- what a page says is complete and true;
- what the spec says a sprint does when it finishes, it does;
- the records each level lists are its own.

### Constraints

- Spec `docs/specs/engine-design-v3.md` for behaviour, the design in
  `docs/design/dashboard-v7/` for the pages (ADR-0020), and ADR-0032 for
  where code goes.
- The owner's design rule for activity: every line is time, action and
  content, with no narrative and no one-off controls.
- Assay: nothing is pushed to its GitLab remote without the owner's word.

### Affected areas

`foreman/engine/`, `foreman/store/`, `foreman/services/`, `foreman/api/`,
`foreman/cli/`, `frontend/src/`, tests, `docs/`.

### Slices

| # | Slice | Status | Executed by | Deliverable |
|---|-------|--------|-------------|-------------|
| 1 | How many tests ran, read from the JUnit XML report the test command writes; the test step's records saved as they happen, so the step shows when the tests started | in_progress | Claude | `feat/test-report-count` |
| 2 | Finishing a sprint as spec §6.4 says: tag the repository, write the checkpoint note when `write_checkpoint_notes` is on, record `engine.checkpoint` | todo | Claude | |
| 3 | Records about a sprint or the engine kept as what they are, not pinned to a task through a made-up run (an ADR first); the sprint says it is ready to finish | todo | Claude | |
| 4 | Repository facts per step: files and lines changed; for a merge, what it brought in, where `main` was, whether the branch was kept | todo | Claude | |
| 5 | The project page's tabs with their controls on the tab line; spend written one way | todo | Claude | |
| 6 | Small gaps: manager replies formatted; a filed task names the task it came from; one event stream per page; `foreman init` and Settings › Runners read the project's own roles and workflows; who finishes a sprint set from the dashboard | todo | Claude | |

### Left for later

Not in this sprint, from "Left to finish the current product" in
`docs/sprints/backlog.md`:
- the limits on work filed by other systems;
- where the database lives, and migrations as a deploy step;
- browser tests for the user's journeys, which go with owner direction 5.

## Before this sprint

Sprint 61, "the core, proven" (stage 1 of the roadmap), closed on
2026-11-20: `docs/sprints/archive/sprint-61-the-core-proven.md` and
`docs/checkpoints/2026-11-20-sprint-61-closed.md`. Since then, at the
owner's request:
- the outcome numbers were put on the project and sprint pages, then taken
  off them again (ADR-0034 amendment);
- the sprint page and a task's Activity, Overview and Checks were
  redesigned one at a time (`docs/sprints/backlog.md`, the sections at the
  top);
- the backlog was checked against the code (2026-11-23).

Stage 2 ("the manager and people") follows this sprint. It starts with an
ADR for the identity system inside Foreman, which the owner reads before
any code is written.
