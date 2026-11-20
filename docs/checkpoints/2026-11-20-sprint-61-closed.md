# Checkpoint: sprint 61 closed (2026-11-20)

Sprint 61, "the core, proven", is complete on `main`. It was stage 1 of the
roadmap in `docs/ROADMAP.md`. Its slices are in
`docs/sprints/archive/sprint-61-the-core-proven.md`.

## What works

- **Outcome numbers** (ADR-0034): `foreman outcomes <project> [--sprint]
  [--json]` and `GET /api/v1/projects/{id}/outcomes` show:
  - tasks that passed first time;
  - send-backs by cause;
  - a person's part;
  - cost per merged task and time to merge, per role and model.

  They are computed from runs and events; nothing new is stored.
- **Lease fencing** (ADR-0011 amendment): an engine whose lease was taken
  over cannot write the task.
- **Corrective retry:** it sends the correction alone. A run left behind by
  a dead engine is recovered at its step.
- **No long functions:** no function in `foreman/` is over 200 lines
  (ADR-0032).
- **CLI reads:** every CLI read command goes through a service and takes
  `--json`. `tests/test_layers.py` holds both.
- **Assay's sprint 2 ran unattended:**
  - Assay's manager planned it from the goal and the owner confirmed it.
  - 8 of 8 tasks merged, 7 of them first time.
  - Nobody was asked anything and nobody stepped in.
  - $0.36 per merged task, median 6.9 minutes to merge.
  - No fault in Foreman was seen.
- **Assay runs as a service:** at `192.168.50.107:8090`, on this machine,
  against its own database (Assay's `docs/DEPLOY.md`).
- **Validation at close:** 1591 Python tests passing, and CI green at
  `165ddc4`, the last code merge.

## What is incomplete

- **Recovery not seen in a real run:** the lease fencing and the stale-run
  recovery are covered by tests. Assay's run did not trigger either.
- **API response models:** deferred (backlog).
- **Outcome numbers on the dashboard:** not shown yet. Where they go is for
  the owner to agree.
- **Agent process:** it still runs as the engine's user with a shell and
  the network.
- **Assay:**
  - The admin token is for the owner to issue.
  - Its roadmap does not yet mark S2 delivered.
  - Its service does not come back after a reboot.

## Next

Stage 2, "the manager and people", starts with an ADR for the identity
system inside Foreman (`docs/sprints/current.md`).
