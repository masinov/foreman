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
| `edit_task` | `task_id`, `title?`, `task_type?`, `description?`, `acceptance_criteria?`, `priority?`, `complexity?`, `depends_on_task_ids?` | `edit_task` |
| `block_task` | `task_id`, `reason` | `block_task` |
| `unblock_task` | `task_id` | `unblock_task` |
| `cancel_task` | `task_id` | `cancel_task` |
| `complete_task` | `task_id`, `reason` | `complete_task`: done by hand, without running its remaining steps |
| `reopen_task` | `task_id` | `reopen_task`: a done or cancelled task back to the queue |
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

## Amendment, 2026-11-15: the session is confined to reading and proposing (FOR-42)

Section 4 ended: "It is not a sandbox: the session still has a shell and
file access ... Restricting the session's tools to the read surface is a
follow-up." This is that follow-up.

A manager turn's Claude Code process is now started with
(`meta_agent.manager_command`, `manager_process_env`):

- `--permission-mode default`, not `bypassPermissions`. In a headless
  session nobody can be asked, so whatever the rules below do not allow is
  refused.
- `--tools Read,Grep,Glob,Bash,Write`: its whole tool set.
- `--allowed-tools Read,Grep,Glob,Bash(foreman:*),Edit(.foreman/manager/**)`.
- `--strict-mcp-config`: none of the dashboard user's own connectors.
- The short agent environment of ADR-0023 plus the session's marks and
  `FOREMAN_DB`, with this installation's `foreman` first on the path.

What that gives, checked against the real CLI (2.1.325):

| The session tries | Result |
|---|---|
| `foreman board <project>` and the other read commands | runs |
| `foreman proposal create <project> --json .foreman/manager/x.json` | runs |
| Write a file in `.foreman/manager/` | allowed |
| Write or edit any other file | refused |
| `ls`, `cat <file in the repository>`, `git status` | runs (the CLI classes them as read-only) |
| `cat <file outside the repository>` | refused |
| `echo hi > note.txt`, `foreman board p && touch x` | refused |
| `FOO=1 foreman board p` (a variable prefix, so also clearing the session mark) | refused |
| `sqlite3 x.db ...`, `python3 -c ...`, `git commit`, `env` | refused |

The manager no longer sends its proposal through a heredoc (the CLI refuses
one that contains JSON). It writes the document to `.foreman/manager/` with
the Write tool and passes the path to `foreman proposal create`. Every turn
after the first carries a five-line reminder of this, so a session begun
under the earlier contract follows it.

Still true: this rests on the Claude Code CLI's permission rules and its
own judgement of which shell commands only read. It is as strong as that,
and it is checked for one CLI version. State changes are still refused a
second time at the Foreman CLI (section 4).

## Amendment, 2026-11-15: closing and reopening by hand, size and dependencies

The vocabulary gains `complete_task` and `reopen_task`, the two operations a
person got in sprint 58 for work finished outside the engine, and
`edit_task` gains `complexity` and `depends_on_task_ids` (an empty list
makes a task wait for nothing). They map to the same `Mutations` methods
the CLI and the task page use, with the same refusals: a task the engine is
running cannot be closed by hand, a task cannot wait for itself or for one
that waits for it, and what a started task waits for cannot change.

`complete_task` needs a reason. The card says "by hand, without running its
remaining steps" beside it, because confirming closes work nothing checked;
the reason is recorded on the task and shown in its Details.

## Amendment, 2026-11-16: planning

The owner decided on 2026-11-16 that planning is not a role or a workflow
step. A task that needs a plan before it can start is too big and is split;
turning a sprint's goal into tasks is what the manager already does. So
planning is one ability of the manager with two requests, both ending in an
ordinary proposal (`foreman/planning.py`):

- **Plan this sprint** (a sprint's More menu, for a planned or active sprint
  that has a goal): the tasks that reach the goal.
- **Split into smaller tasks** (a task's More menu, before it starts):
  smaller tasks that together do what it asks, and the task cancelled.

What changes:

1. **A request is named, not worded.** `POST /api/v1/projects/{id}/meta/message`
   takes `{"plan": {"kind": "plan_sprint", "sprint_id": ...}}` or
   `{"kind": "split_task", "task_id": ...}` in place of a message. The server
   writes what the manager is told (what a good task is, which operations to
   use, what is already in the sprint) and stores only one line as the
   person's message. A request that cannot be planned (no goal, a finished
   sprint, a task already underway) is refused before a turn starts.
2. **`add_task`** is a new operation: a task added straight into a planned
   or active sprint, ready to run. `ref` names it within the proposal, and a
   later `add_task` lists refs or task ids in `waits_for`. Before this a
   proposal could not put a task it created into a sprint, because the task
   had no id until the proposal was confirmed.
3. **"Approve plans" decides who confirms.** The project's `plan_approval`
   policy, which until now only governed a plan gate in a workflow, also
   says who confirms a planning proposal: a person (the default), or
   Foreman. With Foreman, the proposal is confirmed when the turn ends, as
   `foreman` via `policy`, and only if it does what was asked and nothing
   else: `add_task` into that sprint for a plan; the pieces and then
   `cancel_task` of that task for a split. Any other proposal made in the
   turn waits for a person. This is the one case where a proposal is
   confirmed without a person, and it is a setting a person chose.
4. **The card shows what is confirmed.** For each `add_task`: the title,
   size and what it waits for, what it is ("What") and its acceptance
   criteria ("Done when").

Checked with the real manager on a copy of the database: asked to plan a
sprint from a three-part goal, it read the code for 39 tool calls and wrote
five tasks with files named, checkable criteria and two dependencies; that
proposal was stored and confirmed with this code. Not checked: a planning
turn with Foreman approving plans against the real manager (tests only).
