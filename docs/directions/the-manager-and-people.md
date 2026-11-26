# The manager and people (roadmap stage 2)

- Date: owner decisions, 2026-11-19
- Moved from the hand-written `docs/sprints/backlog.md` on 2026-11-26 (FOR-70). The words below are as they were written; only a reference to another section is now a link.

Settled in discussion with the owner on 2026-11-19. Stage 2 of
`docs/ROADMAP.md` builds them, after an ADR.

- **Work is registered.** Everything done through Foreman is listed and
  auditable; no task or feature is developed without being listed. The
  record is kept whole where code enters `main` (only Foreman's merge moves
  it), not by limiting sessions.
- **Identity.** Foreman gets a simple identity system of its own, which a
  company-wide one can replace later. This supersedes the 2026-11-16 line
  "no login, user or role-of-person work until the owner asks".
- **The manager** is the project lead and the person's way of operating
  Foreman. It sees everything and investigates freely (scripts, queries,
  tests run against `main`). It acts directly when a person asks, recorded
  under that person's name; a plan of several tasks is shown before it is
  applied. It writes no code that goes into the product: code comes only
  from tasks. It can adjust how a task is done: per-task model and policy
  overrides, notes to the developer and reviewers, the workflow before the
  task starts, engine control. The FOR-42 write limit (ADR-0022 amendment)
  is revisited with it.
- **One manager conversation per person per project.** What it does lands in
  the project's shared activity. There is no conversation owned by no one.
- **Roles:** owner (at least one per project; controls everything in it) and
  member. A client is a task's reporter, not a user.
- **Two decisions per task:** who is responsible, and whether it is accepted
  (or declined, or changed in type and accepted). They are independent: a
  ticket can name its responsible person and still be declined by them. A
  task runs only when it is accepted and has a responsible person.
  - A member filing their own work: responsible and accepted at once.
  - A member may file work for others to pick up; they are its reporter.
  - An owner may assign anyone; the person is notified.
  - A task with nobody responsible: any member or owner decides; whoever
    accepts it becomes responsible, unless an owner names someone.
  - A task from an external system waits; a connector may name the
    responsible person when that person is in the project.
  - Derived work (an agent's follow-up, a split) inherits the responsible
    person of the work it came from.
  - A person's manager acts as that person, with their rights.
- **Handing over:** offered and accepted between members; an owner reassigns
  directly; a person who leaves the project hands back to the owners.
- **Notices** go to the responsible person and always to owners, who also
  see what is waiting, on whom and since when, and can act.
- **Conflicts:** a change to someone else's work is a request to its
  responsible person or an owner (the proposal card, used for this). A
  change based on an out-of-date task is refused, saying what changed and
  by whom. Code conflicts stay with the merge.
- **Permissions:** a worker's freedom depends on the machine and what it can
  reach. Gates sit at the boundaries (entering `main`, shared or production
  resources, deploying) as policies with defaults a project can change.
- **Deferred:** decisions sent back to a ticketing app (owner: "let's not try
  to close absolutely everything right now").
