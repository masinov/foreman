# Shared compute, through a cluster manager, only when configured

- Date: 2026-11-18
- Moved from the hand-written `docs/sprints/backlog.md` on 2026-11-26 (FOR-70). The words below are as they were written; only a reference to another section is now a link.

**Shared compute, through a cluster manager, only when configured.**
Foreman does not manage shared GPUs and CPUs: the company's people use
them too. A project can point Foreman at a cluster manager, such as Ray,
and a task's agent or a workflow step then submits jobs with resource
requests. Foreman records each job on the task (waiting, where, how
long, log, result) and enforces limits on it.
