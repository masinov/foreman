# The views, thought through as one system

- Date: owner, 2026-11-23; the left bar 2026-11-26
- Moved from the hand-written `docs/sprints/backlog.md` on 2026-11-26 (FOR-70). The words below are as they were written; only a reference to another section is now a link.

**The views, thought through as one system (owner, 2026-11-23).**
The owner has proposed several views over time. Before any one of them
is built, they are designed together: roadmap stage 5, the left bar.
- **The views proposed so far:**
  - board and sprints;
  - backlog;
  - activity;
  - statistics (agents over many sprints);
  - tests (see [tests that are designed](tests-designed-not-only-watched.md));
  - docs, from which the spec editor may grow. The spec editor may also
    be its own app that talks to Foreman;
  - resources;
  - people and the manager (roadmap stage 2);
  - settings;
  - at workspace level: projects, shared roles and workflows, machines
    and the workers on them (see [central server and workers](central-server-and-workers.md); ADR-0043: which workers run,
    idle or on which task, their restarts; owner, 2026-11-26);
  - on the sprint: its workflow's checks and releases (see
    [releases and deployment through CI/CD](releases-and-deployment-through-ci-cd.md) and
    [workflows above the task](workflows-above-the-task.md));
  - open, not decided (owner, 2026-11-23):
    - a view of the code;
    - a view of the repository's history: branches, commits, merges and
      the tags of finished sprints.
- **To settle for all of them at once:**
  - at which level each view lives (workspace, project, sprint, task);
  - what is a view of its own and what is a tab inside one;
  - how a view links to the others (from a test to its task, and from
    a task to the requirement it touches);
  - where the manager chat sits beside them;
  - how it all works on a phone.
- **Already decided:**
  - the four levels;
  - one screen at a time.
- **The left bar (owner, 2026-11-26):** every view is an entry of a menu
  down the left side of the screen, as Claude's and ChatGPT's web apps
  have it; choosing a view can open its own submenu beneath it, which
  allows deeper navigation than a top bar. Whether the breadcrumb stays
  is decided with it: the left bar may make it redundant. To settle in
  the design: where the project switcher and the four levels sit in the
  bar, what the submenus hold (a project's sprints, a sprint's tasks?),
  what is left in the top bar, and the bar on a phone (a drawer).
- **No longer a rule:** "no code browser" (2026-06-16). It came from
  seeing Foreman as working beside VS Code. Since 2026-09-03 and
  2026-11-19, Foreman is where the work is done: people specify, accept,
  supervise and correct, and VS Code is the occasional hands-on
  exception (owner, 2026-11-23).
- **The order:** one design reference for the whole set comes first,
  then one view at a time, each from a mockup.
