# Sprint 65 as it was opened (2026-11-26)

The hand-written `docs/sprints/current.md` of sprint 65, kept here when
Foreman began writing that file from its database (ADR-0040). The goal and
the tasks are in the database and in the generated copy; the method, the
constraints and the preparation are only here. Task states below are as they
were on the day the sprint opened.

## Sprint 65 — the method, second part

- **Opened:** 2026-11-26 (owner: "Go on. The 'moving up the ladder' must be
  configurable." Then: "Go".)
- **Method:** through Foreman, as sprint 63: merges are approved by Foreman
  (`merge_approval = auto`) and the sprint is finished by Foreman
  (`sprint_completion = auto`). Claude keeps a watchdog that steps in only
  for faults (a blocked task, a stopped worker, a red CI run), and has each
  task reviewed independently once the sprint is finished. It is the first
  sprint run under the holds of ADR-0043.

### Goal

ADR-0040's build items 4 to 6, and the rule for moving up a role's models:
- a change writes its own change file, and Foreman generates the changelog;
- an ADR is numbered when it merges, with a generated index;
- Foreman writes the status, sprint and backlog copies, and `docs/prs/` is
  retired;
- a step moves up its role's models only after failures of its own work,
  as each role sets (configurable per role, at the workspace and the
  project, and per task); the size label goes.

### Constraints

- ADR-0040 and ADR-0041 for what is built, the spec for behaviour, the
  design in `docs/design/dashboard-v7/` for the pages (ADR-0020), and
  ADR-0032 for where code goes.
- Until each ADR-0040 item lands, the rules in `AGENTS.md` still hold.
- One task at a time (ADR-0039).
- The worker runs the code it started with, so its prompts are the ones
  from before the sprint; each branch's own `AGENTS.md` carries the new
  rules as they land.

### Tasks

| Key | Task | Depends on | Status |
|-----|------|------------|--------|
| FOR-67 | A change writes its own change file, and Foreman generates `CHANGELOG.md` | none | todo |
| FOR-68 | An ADR is numbered when it merges, and its index is generated | FOR-67 | todo |
| FOR-69 | Foreman writes the status and sprint copies, and `docs/prs/` is retired | FOR-67 | todo |
| FOR-70 | Foreman writes the backlog's copy, and the owner's directions are one file each | FOR-69 | todo |
| FOR-71 | A step moves up its role's models only after failures of its own work, as each role sets | none | todo |
| FOR-72 | The size label goes | FOR-71 | todo |

The full description and acceptance criteria of each task are in Foreman.

### Before the sprint

- The open items of `docs/sprints/backlog.md` ("Found while reviewing
  sprint 63", "Found while running sprint 62", "Left to finish the current
  product") were filed into Foreman's backlog as FOR-73 to FOR-91, so that
  FOR-70 can replace the file. ADR-0043 part 3 (a worker killed hard leaves
  no agent behind, and a supervisor) is FOR-91.

## Before this sprint

Sprint 63, "the method, first part", was completed on 2026-11-25:
`docs/sprints/archive/sprint-63-the-method-first-part.md`. Sprint 64 was a
one-task trial of its reviewer. On 2026-11-26 ADR-0043 (the work is paused,
not the engine) was built by hand.
