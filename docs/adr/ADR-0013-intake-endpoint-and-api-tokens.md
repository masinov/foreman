# ADR-0013: Intake Endpoint And API Tokens

- Status: accepted
- Date: 2026-09-08
- Deciders: engine team

> The sprint task named this ADR-0012 and its migration 16. Both numbers were
> taken by the worktree-per-task slice that landed first, so this decision is
> ADR-0013 and its migration is 17. Nothing else about the task changed.

## Context

Foreman can only be handed work two ways: `foreman task add` and the dashboard.
Both assume a person is present and both assume a sprint already exists to put
the task in. The production readiness review's "Intake from anywhere"
(`docs/reviews/production-readiness-review.md`) requires a third door — one
project-level endpoint an incident tracker, a chat bot, or a CI job can call
without a human in the loop.

Four questions had to be settled before that endpoint could exist:

1. **What credential does a machine present?** The dashboard's shared token is
   a session key: every holder is the same actor (MANUAL §17), it cannot be
   revoked for one caller, and it opens every route including the manager chat,
   which runs a full-access agent on the server. Handing that to a webhook is
   not acceptable.
2. **How is the secret stored?** A credential that a database dump turns into
   access is a liability, not a credential.
3. **What stops a duplicate?** Webhooks retry, alerts re-fire, and CI jobs are
   re-run. Naively, one incident becomes five tasks.
4. **Where does a task go when the caller does not name a sprint?** A machine
   filing an incident does not know or care what sprint is running.

## Decision

### 1. A separate, named, per-project credential

Migration 17 adds `api_tokens`: `(id, project_id, name, token_hash,
scopes_json, created_by, created_at, last_used_at, revoked_at)`, cascading from
`projects`, with a unique index on `token_hash`. Tokens are minted by `foreman
token create <project> --name NAME` and managed with `token list` / `token
revoke`.

The two credentials are kept strictly apart, and the separation is enforced in
the dashboard's token middleware in both directions:

- the shared dashboard token is **not** accepted on the intake route,
- a project API token is refused with 403 on every other `/api` route.

The second half holds whether or not a dashboard token is configured, so a
leaked intake token cannot be replayed as a dashboard session on a loopback
bind that has no token at all. The middleware recognises an API token by its
`fmn_` prefix, which costs no database round trip; the intake route then
authenticates the secret properly against the store.

Revocation writes a timestamp rather than deleting the row, because tasks carry
`created_by = "api:<token name>"` and the audit trail should still resolve.

### 2. SHA-256, and the secret is never stored

`foreman/api_tokens.py` owns minting and hashing so no other module re-derives
the format. `mint_token_secret()` returns `fmn_` + 32 random bytes, URL-safe
encoded. Only `hash_token_secret()`'s output is persisted; the secret is
printed once by the CLI, returned once by `create_api_token`, and never written
to SQLite, a log line, or an event payload.

A single SHA-256 pass is the right primitive here, not a slow KDF like bcrypt
or Argon2. Those exist to make *low-entropy* human-chosen passwords expensive
to guess. A 256-bit random secret has nothing to brute force, and authentication
happens on a request path where a deliberately slow hash would be a denial-of-
service surface rather than a defence.

### 3. Idempotency on `(project, source.system, source.external_ref)`

The caller's own identifier for the work is the idempotency key. A repeat
returns **200** with the existing task and `created: false`; a first call
returns **201** with `created: true`.

The key is the caller's, not Foreman's, because the caller is the one that
retries: PagerDuty knows it is re-delivering `INC-42` even when it has no idea
what Foreman did the first time. A generated key would require callers to store
Foreman state, which is exactly the coupling an intake endpoint should avoid.

A repeat returns the existing task **unchanged**. Intake creates; it does not
edit. A caller with no `source.system` or no `source.external_ref` has supplied
nothing to match on and gets a new task each time — the guarantee is offered,
not imposed.

### 4. The intake queue is a sprint

> Superseded by ADR-0021 (2026-11-12): work filed without a `sprint_id` now
> goes to the project's backlog, which is not a sprint and never runs.
> Migration 21 moved each intake queue's waiting tasks into it.

When no `sprint_id` is given, the task goes to a per-project sprint with
`id = "<project>-intake"`, titled "Intake queue", created on first use.

**Sprints stay the unit of grouping. A continuous queue is a sprint that never
completes.** The alternative — a task that belongs to no sprint — would have
made `sprint_id` nullable on `tasks` and forced every consumer (the engine's
task selection, the board, the sprint views, the digest, the context
projection) to grow a second code path for orphans. One standing sprint costs
nothing and every existing surface renders it correctly.

Its status follows the project:

- created `active` when the project has no active sprint,
- created `planned` when one is already running — intake must not displace the
  sprint a team is mid-way through,
- reactivated on a later intake once the project has no active sprint, so
  queued work does not strand behind a sprint that has since finished.

To the resident engine an active intake queue is an ordinary sprint.

### Supporting decisions

- Tasks gain `source_system`, `source_ref`, `source_url`, and `reporter`
  (migration 17, indexed on `(project_id, source_system, source_ref)` — the
  idempotency lookup), serialized as a `source` object and rendered in the task
  drawer.
- Filing emits `intake.task_created` on a synthetic `intake` run carrying the
  source and the token's id and name, so the origin is in the event stream and
  not only in a column.
- Intake tasks start as `todo`. The triage status arrives with the policy
  matrix in the next slice.
- Authentication outcomes are two service errors — `DashboardAuthError` (401)
  and `DashboardPermissionError` (403) — so `dashboard_service` decides what
  happened and `dashboard_backend` only maps it to a status code (ADR-0002,
  ADR-0003).

## Consequences

### Positive

- Any system that can make an HTTP request can hand Foreman work, and retries
  are safe by construction.
- Every machine-filed task names the credential that filed it; revoking one
  integration does not disturb the others or the dashboard.
- A database dump contains no usable credential.
- The scope column is a list from day one, so a later `metrics` or `read` scope
  needs no migration — only a new entry in `API_TOKEN_SCOPES`.

### Negative / Trade-offs

- A lost secret is unrecoverable by design; the remedy is revoke-and-recreate.
- Only one scope (`intake`) exists, so the scope check is currently defensive.
  It is enforced and tested anyway, so the first token minted for another scope
  cannot silently gain intake rights.
- The intake queue can accumulate indefinitely. Nothing prunes or ages it yet;
  triage policy is the next slice.
- The `fmn_` prefix means the shape of the credential is public. That is
  intentional — it is a routing hint, not a secret — but an operator who sets
  the dashboard token to a `fmn_`-prefixed string would find it rejected
  outside intake. The middleware checks the configured dashboard token first,
  so a correctly configured deployment is unaffected.
- Intake cannot update an existing task. Two-way sync with the filing system is
  a separate problem and is not attempted here.

## Alternatives Considered

- **Reuse the dashboard token**: rejected. No attribution, no per-caller
  revocation, and it would give a webhook the manager chat.
- **HMAC request signing** (Stripe/GitHub webhook style): stronger against
  replay, but it requires every caller to implement a signing scheme. Bearer
  tokens over TLS are what an incident tracker or a CI job can actually send
  today. Signing can be added later as a second scheme.
- **Foreman-generated idempotency keys**: would force callers to persist
  Foreman state to retry safely.
- **Nullable `tasks.sprint_id` for unsprinted work**: rejected; see §4.
- **A dedicated `intake_requests` table** with promotion into tasks: a real
  option once triage policy lands, but today it would add a table whose rows
  are copied one-to-one into tasks. Deferred until triage needs to hold
  something a task cannot represent.
