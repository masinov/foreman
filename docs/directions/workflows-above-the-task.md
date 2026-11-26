# Workflows above the task: a sprint workflow

- Date: 2026-11-18 (owner's question); the real run of 2026-11-20
- Moved from the hand-written `docs/sprints/backlog.md` on 2026-11-26 (FOR-70). The words below are as they were written; only a reference to another section is now a link.

**Workflows above the task: a sprint workflow (owner's question,
2026-11-18; leads into
[releases and deployment through CI/CD](releases-and-deployment-through-ci-cd.md)).**
- **Today:** workflows are per task only. A sprint's life is fixed in
  code (`foreman/engine/sprints.py`, ADR-0025): activated, its tasks run,
  finished by a person or by the engine. A run must belong to a task.
- **The idea:** a declarative sprint workflow with steps before its tasks
  (plan, plan gate) and after them. After them come checks on the
  integrated `main`, a release gate, the release pipeline, its
  observation, and notes.
- **The loop it allows:** a failing sprint-level check files fix tasks
  into the same sprint, and the sprint runs again until its checks pass.
  No task workflow can express that.
- **Global roles (owner, 2026-11-18):** roles triggered at the end of a
  sprint that look at the whole sprint, not at one task. This is where a
  judge of the sprint's acceptance belongs; the per-task criteria judge
  was removed (ADR-0010 amendment).
- **Further out:** recurring and event-triggered loops at project level,
  which create tasks or sprints and stop there.
- **Seen in a real run (2026-11-20, Assay sprint 2).** All eight tasks
  merged, but Assay's `docs/ROADMAP.md` still lists S2 as not delivered,
  because none of the tasks was asked to update it. Closing a sprint's
  records is a step after its tasks, and only a sprint workflow can
  express it. Owner: "A friction noted in favor of the suggestion i made
  before."
