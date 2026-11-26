# Dependencies across sprints

- Date: owner, 2026-11-26, from ADR-0043
- Moved from the hand-written `docs/sprints/backlog.md` on 2026-11-26 (FOR-70). The words below are as they were written; only a reference to another section is now a link.

**Dependencies across sprints** (owner, 2026-11-26, from ADR-0043:
"Pause should pause the task and everything downstream that depends on
it. We need a way to define and set dependency so that this works").
Today a task can wait only for tasks of its own sprint, set before it
starts, and sprints follow each other in queue order. That is enough
for ADR-0043's pause, and ADR-0043 adds the reverse view ("Needed by").
When sprints or workers run side by side, a task (or a sprint) will
need to wait for work in another sprint, and a pause will follow those
links too. For the future.
