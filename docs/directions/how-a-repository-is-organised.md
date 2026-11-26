# How a project's repository is organised

- Date: owner, 2026-11-24; decided 2026-11-25 (ADR-0040)
- Moved from the hand-written `docs/sprints/backlog.md` on 2026-11-26 (FOR-70). The words below are as they were written; only a reference to another section is now a link.

**How a project's repository is organised (owner, 2026-11-24).** Which
documents a project keeps, where each lives, and who writes it when. This
is for Foreman's own repository and, through `foreman init`, for every
project it runs. The aims, in the owner's words:
- standard, and good practice;
- useful for robust development;
- easy for agents to navigate, easy for users to find things in, and
  auditable;
- without frictions and collisions.

"Keep things tidy for now. Discussing the organization of the work
requires care and online research."
- **Decided 2026-11-25** after the research: ADR-0040 (with the
  proposal `docs/proposals/2026-11-24-method-repository-parallel-work.md`).
  The notes below are kept as the record.
- **First raised** as finding 23 of the sprint 54 run
  (`docs/reviews/sprint-54-live-run-notes.md`, 2026-09-08), "major
  (structural)": the shared files every branch edits at the top collide
  whenever two branches overlap. It was not carried into this backlog
  then, and was raised again on 2026-11-24.
- **The facts, 2026-11-24.** Merges, of the last 300, that touched each
  file:
  - `CHANGELOG.md` (one 140 KB file): 216;
  - `docs/STATUS.md`: 130;
  - `docs/sprints/current.md`: 130;
  - `docs/ARCHITECTURE.md` (986 lines): 88;
  - `docs/MANUAL.md` (2,015 lines): 73;
  - `docs/sprints/backlog.md`: 66;
  - the ADR index: 24.

  Folder sizes: `docs/prs/` 314 files (2.6 MB),
  `docs/sprints/archive/` 50, `docs/checkpoints/` 26.

  Two branches can both take the next ADR number. In sprint 62, FOR-50
  and FOR-52 each went back to develop once because of these files: a
  develop pass, a test run and a second approval each.
- **A first sketch** (Claude, 2026-11-24; a starting point for the
  research, not a decision):
  - each fact has one home: what Foreman's database holds (sprints,
    backlog, status, what each task did) is not kept by hand in
    markdown, and any markdown copy is generated;
  - a task's branch touches only files about its own change;
  - logs are one file per entry: changelog fragments gathered at
    release, ADR numbers given at merge with a generated index;
  - `docs/prs/` becomes the task's own record;
  - the manual and the architecture split by topic;
  - `foreman init` sets the standard up.
- **To research before deciding:**
  - how established projects and agent-driven repositories organise
    docs and agent instructions (AGENTS.md conventions, docs-as-code,
    Diátaxis);
  - changelog fragments (towncrier, changesets, scriv);
  - ADR practice (MADR, numbering at merge, generated indexes);
  - what auditors and users expect to find, and where;
  - what is regenerated, and when it is written (sprint finish,
    release).
