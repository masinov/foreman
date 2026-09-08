# PR Summary: feat/task-add-the-intake-endpoint-and-api-tokens-v2

## Summary

- Sprint 54 slice 5. Foreman can now be handed work by a system rather than a
  person: `POST /api/projects/{id}/intake` files one task from a JSON body,
  authenticated by a named per-project API token.
- Tokens are minted and managed with `foreman token create|list|revoke`. The
  secret (`fmn_` + 32 random bytes) is shown once; only its SHA-256 is stored,
  so a database dump yields no usable credential.
- Intake is **idempotent on the caller's own key** `(project, source.system,
  source.external_ref)` — a re-delivered webhook is one task, returned
  unchanged. 201 with `created: true` for new work, 200 with `created: false`
  for a repeat.
- Work filed without `sprint_id` lands in the project's **intake queue**, a
  standing sprint `<project>-intake`. Sprints stay the unit of grouping; a
  continuous queue is a sprint that never completes.
- The two credentials are kept strictly apart: the shared dashboard token is
  refused on intake, and an API token is refused with 403 on every other `/api`
  route — whether or not a dashboard token is configured.

### Numbering note

The task specified **migration 16** and **ADR-0012**. Both were already taken
by the worktree-per-task slice (`chore/task-c68378a4e541` / slice 4) that
landed before this branch started. This work is therefore **migration 17** and
**ADR-0013**; migration 17 is verified to apply to a version-16 database.
Nothing else about the task's scope changed.

## Scope

In:

- `api_tokens` table, task source columns, and the store methods over them,
- the `foreman token` CLI,
- the intake endpoint, its service method, and the middleware credential rule,
- `source` in task serialization and a Source section in the task drawer,
- docs, ADR, and tests.

Out (later tasks, per the task description):

- triage policy and the `triage` status — intake tasks land as `todo`,
- notifications,
- two-way sync back to the filing system; intake creates, it never edits.

## Files changed

New:

- `foreman/api_tokens.py` — the only module that mints or hashes a token
  secret, plus the scope vocabulary.
- `tests/test_intake.py` — 50 tests.
- `docs/adr/ADR-0013-intake-endpoint-and-api-tokens.md`.

Changed:

- `foreman/migrations.py` — migration 17.
- `foreman/models.py` — the `ApiToken` dataclass; `Task` source fields.
- `foreman/store.py` — `create_api_token`, `find_api_token`, `get_api_token`,
  `list_api_tokens`, `revoke_api_token`, `find_task_by_source`; task source
  columns in `save_task` / `_row_to_task`.
- `foreman/dashboard_service.py` — `authenticate_intake`, `intake_task`,
  `_ensure_intake_sprint`, `_normalize_intake_source`, `_serialize_task_source`;
  `DashboardAuthError` / `DashboardPermissionError`; `_ensure_event_run` gains
  an author.
- `foreman/dashboard_backend.py` — the intake route, the middleware rule, and
  401/403 exception handlers.
- `foreman/cli.py` — `foreman token create|list|revoke`.
- `frontend/src/components.jsx`, `styles.css`, `components.test.jsx` — the
  drawer's Source section.
- `foreman/dashboard_frontend_dist/` — rebuilt.
- `tests/test_worktrees.py` — one assertion that hard-coded schema head 16.
- `docs/MANUAL.md` (new §25, renumbered Troubleshooting to §26, CLI reference,
  endpoint map, event taxonomy, migration table, troubleshooting rows),
  `README.md`, `docs/ARCHITECTURE.md`, `docs/adr/README.md`, `CHANGELOG.md`.

## Migrations

**17** — `add api_tokens and task source columns: work arriving from other
systems`:

- `api_tokens (id, project_id → projects ON DELETE CASCADE, name, token_hash,
  scopes_json, created_by, created_at, last_used_at, revoked_at)`,
- unique index `idx_api_tokens_hash` on `token_hash`; `idx_api_tokens_project`
  on `(project_id, created_at)`,
- `tasks.source_system`, `tasks.source_ref`, `tasks.source_url`,
  `tasks.reporter` (all nullable `ALTER TABLE ADD COLUMN`),
- `idx_tasks_source` on `(project_id, source_system, source_ref)` — the
  idempotency lookup.

Additive only: no `RETURNING`, no `DROP COLUMN`, no table rebuild, so it is
within the bundled SQLite 3.31 limits (ADR-0005). Tested against a database
built up to version 16 and stopped there.

## Risks

- **A new credential type.** Mitigated by hashing (nothing reusable at rest),
  by per-project scoping, by revocation, and by the middleware refusing an API
  token everywhere except intake. The riskiest remaining path is an operator
  pasting a secret somewhere it is logged — outside Foreman's control, which is
  why the CLI says the secret is shown once and why nothing in the codebase
  writes it.
- **A changed middleware on every `/api` request.** The dashboard token path is
  unchanged in behaviour and covered by the existing dashboard suite plus a new
  test that the shared token still opens the other routes.
- **The intake queue can grow without bound.** Nothing ages or prunes it; that
  is triage policy's job in the next slice.
- **Idempotency is scoped to a `(system, external_ref)` pair.** A caller that
  sends neither gets a new task per call. This is documented, tested, and
  deliberate — there is nothing else to match on — but a sloppy integration can
  still create duplicates.
- **Task ids are derived from the title**, so two differently-referenced
  incidents with the same title get `-2`-suffixed ids. Pre-existing behaviour
  shared with `create_task`, not introduced here.

## Tests

```
./venv/bin/python -m unittest discover -s tests     # 882 tests, OK (1 skipped)
npm --prefix frontend test                          # 38 tests, 4 files, passed
npm --prefix frontend run build                     # built, dist committed
./venv/bin/python scripts/validate_repo_memory.py   # passed
```

`tests/test_intake.py` (50 tests) covers:

- **secrets** — prefix and uniqueness of minted secrets, stable SHA-256, empty
  secret rejected, scope defaulting and rejection, and that a dashboard token
  is not mistaken for an API token;
- **store** — create returns a record and a one-time secret; the secret is
  absent from the raw database file while its hash is present; find matches,
  records the use, and rejects wrong or empty secrets; revoke stops
  authentication, keeps the row listed, and is idempotent; tokens cascade with
  their project;
- **migration** — 17 applies to a version-16 database and creates the table and
  columns; two tokens cannot share a hash;
- **service** — source fields persisted, `created_by = "api:<name>"`, status
  `todo`; the same reference returns the same task untouched; a different
  reference is new work; no key means no idempotency; the queue is created
  `active`, created `planned` under a running sprint, and reactivates once that
  sprint completes; an explicit sprint bypasses the queue and one from another
  project is rejected; the event carries the source and the token's identity
  but not the secret, on an `intake`/`api` run; the response equals
  `get_task` + `created`; six malformed payloads are rejected before anything
  is written; auth separates 401 from 403, including a token minted for a
  future non-intake scope;
- **endpoint** — 401 with no token, with the dashboard token, and with a
  revoked token; 403 for another project's token; 201 then 200; the response
  carries the source and the creating token; 400 for a missing title; 403 (not
  a 404 existence leak) for an unknown project; an API token refused on three
  other `/api` routes and on `GET /api/projects` with no dashboard token
  configured; the dashboard token still opens the other routes;
- **CLI** — create prints the secret once and stores only its hash, needs a
  name, rejects an unknown scope and an unknown project; list shows tokens and
  never a secret and says so when empty; revoke stops authentication and
  refuses a token from another project.

Frontend: three drawer tests (source rendered, reference linked with
`rel=noopener` when a url is present, no Source section for a person's task).

No test invokes a real `claude` or `codex` binary; intake files a task and
returns without an agent.

One pre-existing test changed: `test_migration_16_applies_cleanly_to_a_version_15_database`
asserted schema head `== 16`, which any later migration breaks. It now asserts
16 applied and head is the latest migration.

## Screenshots or output examples

```console
$ ./venv/bin/foreman token create foreman --name pagerduty
API token created
Project: foreman | Foreman
Token: tok-3e69a2a2649c | pagerduty
Scopes: intake

  fmn_M2jJs9H9bkn9-C3u471JJwfFg51jIiJw1CH1L1ONceA

This secret is shown once and is not stored — only its SHA-256 is.
Copy it now; if it is lost, revoke this token and create another.

$ ./venv/bin/foreman token list foreman
API tokens
Project: foreman | Foreman
- tok-3e69a2a2649c | pagerduty | active
  scopes=intake | created=2026-09-08T12:48:48Z | last_used=never

$ curl -X POST localhost:8000/api/projects/foreman/intake \
    -H "Authorization: Bearer fmn_M2jJ..." \
    -d '{"title":"Disk full on web-3",
         "source":{"system":"pagerduty","external_ref":"INC-42"}}'
HTTP 201  {"id": "task-disk-full-on-web-3", "task_key": "FOR-9",
           "status": "todo", "created_by": "api:pagerduty",
           "source": {"system": "pagerduty", "external_ref": "INC-42",
                      "url": null, "reporter": null},
           "created": true}

# the same call again
HTTP 200  {"id": "task-disk-full-on-web-3", ..., "created": false}

$ ./venv/bin/foreman db version
Schema version: 17 (up to date)
```

## Acceptance criteria satisfied

- ✅ Migration creates `api_tokens` and the task source columns and applies
  cleanly to the previous version — **17 on a version-16 database**, not 16 on
  15, because 16 was taken; `foreman db version` reports 17.
- ✅ `foreman token create|list|revoke` work; the secret is printed once and
  only its SHA-256 is stored.
- ✅ Intake returns 401 without a bearer token (and for the dashboard token or
  a revoked one), 403 for another project's token or one without the `intake`
  scope, 201 `created: true` for a new `(system, external_ref)`, 200
  `created: false` for a repeat; API tokens are rejected on every other `/api`
  route.
- ✅ A task posted without `sprint_id` lands in the intake queue sprint,
  created on first use and activated when no sprint is active.
- ✅ The task stores `source_system`, `source_ref`, `source_url`, `reporter`,
  has `created_by = "api:<token name>"`, and emits `intake.task_created`.
- ✅ The task drawer shows the source; `foreman/dashboard_frontend_dist/` is
  rebuilt.
- ✅ Backend suite, frontend tests, frontend build, and
  `scripts/validate_repo_memory.py` all pass.
- ✅ `docs/MANUAL.md`, `README.md`, `docs/ARCHITECTURE.md`, `CHANGELOG.md`, the
  ADR, and this PR note are updated.

## Follow-ups

- **Triage policy** (next sprint task): the `triage` status, routing rules, and
  what to do with an intake queue that grows.
- **Notifications** back to the filing system when a task moves — the other
  half of "intake from anywhere".
- **Queue hygiene**: nothing ages, prunes, or caps the intake queue yet.
- **Token rotation**: revoke-and-recreate is the only path; there is no overlap
  window for a caller that cannot be redeployed atomically.
- **Rate limiting**: intake is unauthenticated-cheap to hammer with a valid
  token. Not a concern on a loopback bind; worth a look before a public one.
- **`last_used_at` writes on every request.** One small `UPDATE` per intake
  call. Fine at current volume; if intake ever becomes hot, coarsen it.
