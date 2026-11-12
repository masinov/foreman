# PR Summary: feat/task-manager-proposes-a-person-confirms

## Summary

- The manager no longer changes project state itself. It proposes, and
  nothing happens until a person confirms (design README, `06-manager-open.html`,
  `05-task-overview.html`). ADR-0022 records the decision and supersedes
  ADR-0007.
- A proposal is a stored record: who proposed it, when, a reason, an ordered
  list of operations from a fixed vocabulary of 15 kinds (each one
  `Mutations` operation), the tasks it leaves, and the names of what it
  names. States: `proposed`, `confirmed`, `declined`, `failed`.
- Creating a proposal checks it by applying the operations in order inside a
  transaction that is always rolled back. If one is refused, the reason is
  reported with its position and nothing is stored. Confirming applies the
  operations in one transaction with the confirming person as the actor and
  `proposal_id` on every audit event. If one is refused, nothing is applied
  and the proposal is `failed` with the operation and the reason.
- Inside a manager session (the runner sets `FOREMAN_MANAGER_SESSION` and
  `FOREMAN_MANAGER_TURN`), the CLI refuses every command except the read
  commands and `proposal create|list|show`. The refusal is a sentence that
  says to create a proposal. The operating contract and the supervision
  digest now say the same thing.
- The manager stream emits `{"type": "proposal", "proposal_id"}`, and the
  turn stores the id. The side bar renders a card that says what will be
  created, changed and left, with "Not now" and "Confirm". Deciding calls the
  API, shows the outcome on the card, and reloads the page's data. Earlier
  proposals show their final state.
- The narrow-width overlay is a modal region now. It takes focus, keeps Tab
  inside, closes on Escape, and gives focus back to the toggle. It also
  stretches to the viewport, so the composer stays on screen. Before this, it
  grew with its content and pushed the composer below the screen.

## Scope

- Backend: migration 22, `ProposalStore`, `store.atomic()`,
  `foreman/proposals.py`, new `Mutations` operations (`create_sprint`,
  `edit_sprint`, `edit_task`, `record_guidance`, `decide_gate`, `send_back`,
  plus deferred worktree removal). The dashboard service's sprint creation,
  sprint and task edits, guidance and gate decisions now go through those
  operations.
- CLI: `foreman proposal create|list|show|confirm|decline`, the manager
  session guard in `foreman.cli.parser.main`, and `FOREMAN_DB` as a database
  default.
- API: `GET /api/v1/projects/{id}/proposals` (`state`, `limit`, `offset`),
  `GET /api/v1/proposals/{id}`, `POST /api/v1/proposals/{id}/confirm|decline`.
- Manager: environment marks, the `proposal` stream event, the operating
  contract, and the supervision digest wording.
- Frontend: `api/proposals.js`, `useDataRefresh` in `ApiProvider`
  (`useResource` reloads on refresh), `ProposalCard`, `proposalWords.js`,
  `ui/focus.js` (shared with `Dialog`), the overlay's focus trap and Escape,
  and the thread following its end while a card loads.
- Out of scope, as the task says: rendering Markdown in replies, and the "Ask
  the manager" banner.

## Files changed

- `docs/adr/ADR-0022-manager-proposes-person-confirms.md` (new),
  `docs/adr/ADR-0007-sprint-planner-chat-session.md` (superseded),
  `docs/adr/README.md`
- `foreman/migrations.py`, `foreman/models.py` (`Proposal`, `PROPOSAL_STATES`),
  `foreman/store/proposals.py` (new), `foreman/store/__init__.py`,
  `foreman/store/base.py` (`_Connection`, `atomic`)
- `foreman/proposals.py` (new), `foreman/mutations.py`,
  `foreman/dashboard_service.py`
- `foreman/cli/proposals.py` (new), `foreman/cli/parser.py`,
  `foreman/cli/common.py`
- `foreman/dashboard/routers/proposals.py` (new), `foreman/dashboard/app.py`
- `foreman/meta_agent.py`, `foreman/digest.py`
- `frontend/src/api/proposals.js` (new), `frontend/src/api/ApiProvider.jsx`,
  `frontend/src/api/useResource.js`, `frontend/src/api/manager.js`
- `frontend/src/pages/manager/ProposalCard.jsx` (new),
  `frontend/src/pages/manager/proposalWords.js` (new),
  `frontend/src/pages/manager/ManagerPanel.jsx`,
  `frontend/src/pages/manager/useConversation.js`, `frontend/src/app/manager.js`
  (`useOverlay`)
- `frontend/src/ui/focus.js` (new), `frontend/src/ui/Dialog.jsx`
- `frontend/src/styles/manager.css`, `frontend/src/styles/shell.css`,
  `frontend/src/styles/tokens.css` (`--proposal-term-width`)
- Tests: `tests/test_proposals.py` (new), `tests/test_migrations.py`,
  `tests/test_meta_agent.py`, `tests/test_digest.py`, `tests/test_dashboard.py`,
  `tests/test_cli_package.py`, `tests/test_dashboard_api.py`,
  `frontend/src/pages/manager/ManagerPanel.test.jsx`,
  `frontend/src/pages/manager/proposalWords.test.js` (new),
  `frontend/src/api/resources.test.js`
- Docs: `docs/ARCHITECTURE.md`, `docs/STATUS.md`, `docs/MANUAL.md`, `README.md`

## Migrations

- 22: `proposals` table (CHECK on `state`, `ON DELETE CASCADE` from
  `projects`), plus indexes on `(project_id, created_at)` and `turn_id`.
  `ProposalMigrationTests` upgrades a version-21 database, checks the
  columns, the round trip, the state guard and the project foreign key, and
  checks that the migration is applied only once.

## Risks

- `store.atomic()` wraps the store's connection in `_Connection`, so the
  existing `with self._connection:` blocks join an open transaction instead
  of committing. Outside `atomic` they behave as before. The full suite
  passes. Inside `atomic`, the store holds the write lock for the length of a
  proposal (a dry run or a confirm), so an engine that writes at the same
  moment waits on the busy timeout.
- The guard works at the CLI boundary. It is not a sandbox: the manager
  session still has a shell (`bypassPermissions`) to read the repository, and
  a process that clears the variable or writes SQLite directly is not
  stopped. ADR-0022 says this, and so do STATUS and the MANUAL.
- `MANAGER_SESSION_COMMANDS` is an allowlist, so a new command is refused in
  a session until someone adds it to the list.
- `FOREMAN_DB` is a new default for every command's database: after `--db`
  and a repo path, before repo-local discovery. Nothing sets it outside a
  manager session.
- The dashboard sends no person yet, so `decided_by` is null for a decision
  made there. The surface is recorded in `outcome.via`. A guidance note's
  event id changed shape (it now comes from the mutation service), and one
  test was updated to match.

## Tests

- `./venv/bin/python -m unittest discover -s tests`: 1313 tests, OK
  (1 skipped).
- `tests/test_proposals.py` covers:
  - each operation kind, accepted when it is allowed now;
  - each refusal: shape, existence, and a state refusal for each kind;
  - operations judged in order (accept, then plan);
  - a confirm that applies in order, with the person and `proposal_id` on the
    audit events;
  - a refused confirm that applies nothing;
  - decline, and deciding twice;
  - worktree removal only after a commit;
  - the API (paging, state filter, 404 and 400) and the CLI (file, stdin,
    `list`, `show`, `confirm`, `decline`, a failed confirm);
  - the manager session: each mutating command refused with the sentence,
    read commands still working, `FOREMAN_DB`, a proposal recorded as the
    manager's with its turn, and no proposals for another project.
- `tests/test_meta_agent.py` covers:
  - the session environment;
  - the `proposal` event, in order, and stored in the turn;
  - the real `_run_claude` passing the environment to its process;
  - the contract listing only commands a session may run.
- `npm --prefix frontend test`: 30 files, 305 tests. They cover the card from
  a mocked stream; Confirm, Not now, a failed confirm and an API refusal on
  the card; the page data reloading (the sprint queue is fetched again); an
  earlier proposal showing its final state; the words for each kind; and the
  overlay focus trap, Escape and focus return, with Escape doing nothing
  beside the page.
- `npm --prefix frontend run build`: built. The bundle is ignored and not
  committed, as the sprint rules say (2026-11-12). The acceptance line that
  says to commit it is older than that rule.
- `./venv/bin/python scripts/validate_repo_memory.py`: passes.
- Looked at with Chrome against a copy of the project database
  (`/tmp/for40-shot.db`) on port 8140. I compared the pages with
  `06-manager-open.html` and `05-task-overview.html`, then fixed default
  `dl`/`dd` margins, the term column gap, titles-only rows in "Plan in" and
  "Leave", and the overlay height.

## Screenshots or output examples

All at 1440 wide except the phone one, in
`docs/prs/screenshots/feat-task-manager-proposes-a-person-confirms/`:

- `project-proposal.png`: project page with a proposal waiting (Create,
  Plan in, Leave; Not now, Confirm).
- `project-proposal-confirmed.png`: the same after Confirm. The card says
  "Confirmed. Applied 1 operation.", and the page has reloaded: Sprint 59 is
  planned and Backlog went from 3 to 1.
- `task-send-back-proposal.png`: task page with a send-back proposal ("FOR-31
  to Develop, in place of approving the merge", Guidance).
- `phone-overlay.png`: 390 wide; the overlay with the composer on screen.

```
$ foreman proposal create foreman --json - <<'EOF'
{"reason": "...", "operations": [{"kind": "cancel_task", "task_id": "done1"}]}
EOF
Refused, nothing stored. Operation 1 (cancel a task): Task done1 is already done and cannot be cancelled.

$ FOREMAN_MANAGER_SESSION=foreman foreman task cancel task-x
foreman task cancel: refused. Foreman's manager cannot change project state itself. Propose the change: `foreman proposal create <project> --json <file or ->`; a person confirms it.
```

## Acceptance criteria satisfied

- ADR-0022 states the model, the vocabulary, what a refused operation does
  on confirm, and how the session is prevented from changing state. It is
  listed in the ADR README, and ADR-0007 is marked superseded.
- Migration 22 adds the storage, with a migration test.
- `foreman proposal create` refuses an invalid operation with the reason and
  stores nothing. Tests cover each operation kind and each refusal.
- Confirm applies in order through the mutation service, with the person as
  the actor and a linking audit event. A refusal marks the proposal failed
  and states what was applied (nothing). Decline records who. Tested through
  the API and the CLI.
- A mutating CLI command in a manager session is refused with a sentence
  telling it to create a proposal, and read commands still work. Tested.
- The stream emits `proposal`. The side bar renders the card, Confirm and
  Not now call the API and show the outcome, and the page reloads. Tested
  with a mocked stream and API.
- The overlay traps focus and closes on Escape. Tested.
- Frontend tests pass, the bundle is rebuilt (not committed; see Tests), the
  Python suite passes, and this summary exists.

## Follow-ups

- Restrict the manager session's tools to the read surface, so the boundary
  is not only the CLI (for example `--disallowedTools` for file edits, or a
  read-only database connection).
- The dashboard has no signed-in person yet, so it cannot say who confirmed.
  It should send `requested_by` once the user menu lands (blocked task
  "Workspace settings and the user menu").
- `05-task-overview.html` shows a "Then" row for a send-back ("Tests and
  review run again. Nothing runs until the engine is started.") and a
  one-line summary of earlier proposals ("Earlier in this conversation: a
  proposal for Sprint 57, not confirmed."). The card shows "Then" only for an
  approval it can derive from the workflow. Both need the path a refusal
  takes through the workflow, and a conversation summary.
- At full width the side bar is `position: sticky; height: 100vh` under the
  top bar. Until the page scrolls, the bottom of the composer (Send) is below
  the fold. This was already the case before this branch; it belongs to "Make
  the built pages match the design".
