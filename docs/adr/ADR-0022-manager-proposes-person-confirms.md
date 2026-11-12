# ADR-0022: The Manager Proposes, A Person Confirms

- Status: accepted
- Date: 2026-11-12
- Supersedes: ADR-0007 (the restricted sprint-planner session it describes was never built)

## Context

The design says of the manager: "It proposes changes; nothing happens until
the person confirms" (`docs/design/dashboard-v7/README.md`, `06-manager-open.html`,
the side bar in `05-task-overview.html`).

The manager that shipped (`foreman/meta_agent.py`) is a Claude Code session
with every permission. Its operating contract lists the mutating `foreman`
commands and it runs them itself during its turn: it creates sprints, plans
work, blocks and cancels tasks, approves gates. The side bar can only report
afterwards what the manager already did. ADR-0007 described a restricted
planner session with its own tool layer; that was never built, and its tool
list (direct create/update/delete of sprints and tasks) would still have let
the agent change state without a person.

A proposal has to be something a person can read before anything changes,
and confirming it has to go through the same rules as a person doing the same
thing by hand (`foreman/mutations.py`, ADR-0021).

## Decision

### 1. A proposal is a stored record

Table `proposals` (migration 22), one row per proposal, for one project:

| column | meaning |
|---|---|
| `id` | `prop-<stamp>-<hex>` |
| `project_id` | the project; deleting the project deletes its proposals |
| `proposed_by` | `manager` when made inside a manager session, else who ran the command |
| `session_id`, `turn_id` | the manager session and the conversation turn it was made in, when it was |
| `reason` | one paragraph: why |
| `operations_json` | the ordered list of operations (below) |
| `leaves_json` | task ids the proposal deliberately leaves where they are, so the card can say "Leave" |
| `names_json` | titles and keys of every task and sprint named, as they were when proposed |
| `state` | `proposed`, `confirmed`, `declined` or `failed` (a CHECK constraint) |
| `created_at` | when |
| `decided_by`, `decided_at` | who confirmed or declined it (null when the surface knows no person yet), and when |
| `outcome_json` | after a decision: what was applied, and for `failed` which operation was refused and why |

Only a `proposed` proposal can be confirmed or declined. Nothing else changes a
proposal after it is decided.

### 2. A fixed vocabulary of operations

Every operation maps to exactly one operation of the mutation service
(`Mutations`), the same one the CLI and the dashboard call:

| `kind` | fields | `Mutations` |
|---|---|---|
| `create_sprint` | `title`, `goal?` | `create_sprint` |
| `edit_sprint` | `sprint_id`, `title?`, `goal?` | `edit_sprint` |
| `activate_sprint` | `sprint_id` | `transition_sprint(.., "active")` |
| `finish_sprint` | `sprint_id` | `transition_sprint(.., "completed")` |
| `file_task` | `title`, `task_type?`, `description?`, `acceptance_criteria?`, `priority?`, `complexity?`, `accept?` | `file_task` (into the backlog) |
| `accept_task` | `task_id` | `accept_task` |
| `decline_task` | `task_id`, `reason?` | `decline_task` |
| `plan_tasks` | `task_ids`, and `sprint_id` or `new_sprint: {title, goal?}` | `plan_tasks` |
| `unplan_task` | `task_id` | `unplan_task` |
| `edit_task` | `task_id`, `title?`, `task_type?`, `description?`, `acceptance_criteria?`, `priority?` | `edit_task` |
| `block_task` | `task_id`, `reason` | `block_task` |
| `unblock_task` | `task_id` | `unblock_task` |
| `cancel_task` | `task_id` | `cancel_task` |
| `send_back` | `task_id`, `guidance` | `send_back`: at a gate it is a denial with the guidance; a blocked task goes back to the queue with the guidance as a note |
| `approve_gate` | `task_id` | `decide_gate(.., "approve")` |

An unknown kind, an unknown field, a missing required field or a value of the
wrong type is refused. Operations name only things that exist when the
proposal is made: there are no references from one operation to a sprint
another creates (planning into a new sprint is `plan_tasks` with
`new_sprint`).

The mutation service gained `create_sprint`, `edit_sprint`, `edit_task`,
`record_guidance`, `send_back` and `decide_gate` so that every kind has its
one implementation there; the dashboard's sprint creation, sprint and task
edits, guidance notes and gate decisions now call them too.

### 3. Validation is a dry run; confirming is one transaction

The store gained `atomic(commit=...)`: one `BEGIN IMMEDIATE` transaction that
every store write inside it joins instead of committing on its own.

- **Creating** a proposal applies its operations, in order, inside an atomic
  block that is always rolled back. Each operation therefore sees what the
  ones before it did (accept a task, then plan it). If one is refused, the
  command reports which operation and the mutation service's reason, and
  nothing is stored.
- **Confirming** applies the operations again, in order, against the state at
  that moment, inside one atomic block that commits only if all of them were
  applied. The confirming person is the actor (`via` is `dashboard`, `api` or
  `cli`; `by` is who confirmed), and every task-level audit event carries
  `proposal_id`. The proposal row (its `decided_by` and `outcome`) is the
  audit record of the confirmation itself, including operations that touch
  only sprints, which have no task to hang an event from.
- **If one operation is refused** at confirm time (the state moved since it
  was proposed) the transaction is rolled back: nothing is applied. The
  proposal is marked `failed` with the operation's position, its kind and the
  refusal, and the outcome says that none of the operations were applied.
  "What was applied" is therefore always all of them (`confirmed`) or none
  (`failed`).
- **Effects outside the database** do not run inside the transaction:
  removing a cancelled task's worktree is deferred until after the commit,
  and skipped after a rollback or a dry run. Notifications are only queued
  (ADR-0015), so they commit or roll back with the rest.
- **Declining** records who declined and when; nothing else changes.
- The surface a decision came through (`cli`, `dashboard`) is recorded in
  `outcome.via`, apart from who, which the dashboard can only say once it
  has a signed-in person (it sends `requested_by` when it does).

### 4. The manager session cannot change state itself

- The runner of a manager turn (`meta_agent._run_claude`) sets
  `FOREMAN_MANAGER_SESSION=<project id>` and `FOREMAN_MANAGER_TURN=<turn id>`
  in the environment of the Claude Code process, and `FOREMAN_DB` to the
  database the dashboard uses, so the manager's `foreman` commands read and
  write the same one.
- The CLI's entry point (`foreman.cli.parser.main`) checks every command
  before it runs. Inside a manager session only the read commands (board,
  status, history, transcript, cost, task show/list, sprint list, backlog
  list, worktree list, notify list/deliveries, engine status, projects, roles,
  workflows, db version, token list) and `proposal create|list|show` run. Any
  other command is refused with: "Foreman's manager cannot change project
  state itself. Propose the change: `foreman proposal create <project> --json
  <file or ->`; a person confirms it." `proposal confirm` and `decline` are
  refused too: the manager cannot confirm its own proposals. A manager
  session can only propose for its own project.
- The operating contract (the prompt) lists the read commands and the
  proposal format, and says changes are made only by proposing.
- When a proposal is created during a turn, the manager stream emits
  `{"type": "proposal", "proposal_id": ...}` and the assistant turn stores
  `{"proposal_id": ...}` in its `tool_uses`, so the conversation shows it
  again later with its final state.

This is enforcement at the CLI boundary, where the manager's changes went.
It is not a sandbox: the session still has a shell and file access to read
the repository, and a process that deliberately clears the variable or writes
the database directly is not stopped by it. Restricting the session's tools
to the read surface is a follow-up.

### 5. API

- `GET /api/v1/projects/{id}/proposals?state=&limit=&offset=` (paged,
  newest first; `state` takes one or more states)
- `GET /api/v1/proposals/{id}`
- `POST /api/v1/proposals/{id}/confirm` `{requested_by?}`
- `POST /api/v1/proposals/{id}/decline` `{requested_by?}`

Confirming a proposal that is refused part-way answers 200 with the proposal
in state `failed`: the request did what it was asked (decide), and the outcome
is the proposal's state. Confirming or declining one that is not `proposed`
answers 400 (`invalid_request`), with the error envelope of ADR-0019.

## Consequences

- The design's promise holds for the manager: nothing it asks for happens
  until a person confirms, and a confirmation goes through the same rules and
  leaves the same audit trail as doing it by hand.
- One more step for a person; the side bar card is that step.
- The store's write methods can now be composed into one transaction. Writes
  that open their own transaction outside `atomic` behave as before.
- Proposals made before a confirm may go stale; confirming re-checks
  everything and fails whole, never half-applied.
