# Current Sprint

## No sprint is open

Sprint 59 (the engine can be left running again, the first of Phase 5 of
`docs/reviews/2026-11-10-full-review-and-finish-plan.md`) closed on
2026-11-16: `docs/sprints/archive/sprint-59-engine-left-running.md`,
`docs/checkpoints/2026-11-16-sprint-59-closed.md`.

The engine is stopped (owner, 2026-11-13). Sprint 59's engine fixes are
covered by tests and have not been seen in a run of the engine; whether to
start it again is the owner's call.

### Proposed sprint 60 (not opened; the owner has not agreed its scope)

Goal: Foreman knows who did what. Today every decision is recorded as made
by whoever holds the one dashboard token. No identity provider is chosen
(owner, 2026-11-10); the sprint delivers the seam and one built-in way to
fill it.

| # | Slice | Source |
|---|-------|--------|
| 1 | An ADR for identity: users, the four roles (viewer, operator, approver, admin), where a provider plugs in | Phase 5 |
| 2 | Users and sessions in the database; sign in with a built-in local provider behind the seam | Phase 5 |
| 3 | Every decision (approve, send back, mark done, confirm a proposal, settings) records the actor the server derived, never one the client sent | Phase 5 |
| 4 | Roles enforced on the API and shown in the dashboard: a viewer cannot approve, only an admin changes host-level settings | Phase 5 |
| 5 | Audit events cannot be changed or deleted | Phase 5 |
| 6 | Manager chat through the runner: a declared tool set, a session per user, one turn at a time, stopped when the person leaves, cost per turn | Phase 5 |
| 7 | FOR-43, if accepted: the proposal card's "Then" row for a send-back, a summary line for earlier proposals | `docs/sprints/backlog.md` |

Later Phase 5 sprints: a planner step per task with a protected acceptance
test, pull requests through the remote and a container per task; then the
notification seam, checkpoint tags, Codex, the database out of the
repository and a deployment guide.

A fresh agent should not start sprint 60 until this section is replaced by
an opened sprint.
