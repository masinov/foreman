# Current Sprint

## Sprint 61 — the core, proven

- **Opened:** 2026-11-19, as stage 1 of the roadmap in `docs/ROADMAP.md`
  (owner: "Go with stage 1").
- **Status:** in_progress
- **Method:** by hand, except slice 6, which Foreman runs on Assay.

### Goal

An engine that can be left alone for a whole sprint, and numbers that say how
well its agents do. Every later stage stands on the first and is judged by
the second.

### Constraints

- Spec `docs/specs/engine-design-v3.md` for behaviour; ADR-0032 for where
  code goes (`lint-imports` and `tests/test_layers.py` hold it).
- Slices 3 to 5 change no behaviour that a person or an agent can see,
  except what their row names.
- The owner is asked before a screen's structure changes (the outcome
  numbers' place on the dashboard).
- Assay: nothing is pushed to its GitLab remote without the owner's word; its
  `.env.admin` (the shared server's superuser login) is never given to an
  agent, and no other database on that server is touched.

### Affected areas

`foreman/store/`, `foreman/services/`, `foreman/engine/`, `foreman/cli/`,
`foreman/api/`, `frontend/src/`, tests, `docs/`.

### Slices

| # | Slice | Status | Executed by | Deliverable |
|---|-------|--------|-------------|-------------|
| 1 | Outcome numbers per project, role and model: tasks that passed first time, send-backs, a person's interventions, cost per merged task | done | Claude | `feat/outcome-numbers`: ADR-0034, `foreman outcomes` with `--json`, `GET /api/v1/projects/{id}/outcomes`. The dashboard's place is the owner's to agree |
| 2 | The lease fencing token is checked on writes: a holder whose lease was taken over cannot write | done | Claude | `fix/lease-fencing-on-writes`: ADR-0011 amendment; `FencedWriteError`; a lifecycle test that fails without the fence |
| 3 | The carried engine items: `resume_human_gate` and `_run_leased_task` leave the orchestrator; the agent step's corrective retry sends the correction rather than the first prompt again; a stale `running` agent run is resumed in place | todo | Claude | One branch per item, each with a test |
| 4 | The seven functions over 200 lines split (ADR-0032's list) | todo | Claude | No behaviour change; ADR-0032's "not settled" list updated |
| 5 | The CLI's reads go through services; `--json` on the remaining read commands; response models on the API; statuses as Python enums | todo | Claude | `tests/test_layers.py` extended to reads |
| 6 | Assay runs a whole sprint unattended | todo | Foreman, watched by Claude through its records | Its next sprint planned by its manager from the spec and confirmed by the owner; the engine left running; what went wrong recorded and fixed |
| 7 | Close the sprint: checkpoint, archive | todo | Claude | `docs/checkpoints/`, `docs/sprints/archive/` |

### Risks

- Slices 2 and 3 change how the engine writes and recovers; a fault there
  shows only in a real run, which is why slice 6 comes after them.
- Slice 6 depends on the shared database server, which is slow (Assay's
  suite takes about nine minutes), and on the machine's load from other
  work.

### Validation

Before every merge: `ruff check foreman tests scripts`, `lint-imports`,
`./venv/bin/python -m unittest discover -s tests`,
`npm --prefix frontend run lint`, `npm --prefix frontend test`,
`npm --prefix frontend run build`,
`./venv/bin/python scripts/validate_repo_memory.py`. CI is read after every
push. Dashboard changes are looked at with `scripts/dashboard_shot.mjs`.
