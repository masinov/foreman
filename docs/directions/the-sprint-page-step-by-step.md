# The sprint page, step by step

- Date: owner, 2026-11-21
- Moved from the hand-written `docs/sprints/backlog.md` on 2026-11-26 (FOR-70). The words below are as they were written; only a reference to another section is now a link.

The owner asked for the sprint page to be redesigned a little at a time,
from a mockup first, so less goes wrong at once. "When a user clicks on a
sprint, what should they see first?"

- **Done, the top (`feat/sprint-page-top`):** the title row; the goal,
  four lines then "Show all", beside Details (state, tasks, spend); two
  tabs, Tasks and Activity, each with its controls on the tab line (Add
  from backlog, New task, List | Board; By and All | Problems). Activity is
  the log alone. By names the role, the model on hover, on every activity
  list and on a task's Steps. The outcome line is off the sprint and
  project pages (ADR-0034 amendment).
- **Statistics view (owner):** how well agents do over many sprints, as
  numbers and graphs: first-time passes, send-backs by cause, a user's
  part, cost per merged task, time to merge, by role and model. The data
  is `GET /projects/{id}/outcomes`; where the view lives is decided with
  the other views (see [the views as one system](the-views-as-one-system.md)).
- **Proposed next, one at a time, each from a mockup:**
  - (Done on 2026-11-22, in the task's step panel: the prompt is the
    step's first line, and one button downloads the transcript.)
  - (Done on 2026-11-24, sprint 62 slice 5.) The project page's tabs with their controls on the tab line too (its
    Activity filters and New sprint are under it, in a heading of their
    own), so every tabbed page works the same;
  - small frictions seen on the way. Done on 2026-11-22: "Measured by
    Foreman", the APPROVE line, "Merged in 0.1 s", the review named by its
    role. Still to do: the lone "OK" a test's detail shows (with the test
    count). Spend written three ways: done 2026-11-24 (`ui/Spend`).
