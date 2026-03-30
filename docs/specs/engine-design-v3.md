# Autonomous Development Engine — Design Document v3

## 1. Overview

The engine takes a project spec and drives autonomous agents through a
sprint-based workflow. It manages structured state (projects, sprints, tasks,
runs, events) in SQLite, projects ephemeral context into a gitignored path in
the target repo for agent consumption, and exposes all state through a
queryable store that a CLI or future web UI can read from.

The engine is composed of four layers:

- **Agent Runner** — launches one agent process, streams structured events,
  enforces cost/time gates, retries infrastructure failures
- **Role System** — declarative TOML configuration of agent behavior, prompt
  templates, tool access, and completion criteria
- **Workflow Engine** — composes roles into step graphs with outcome-based
  transitions, gate triggers, loop limits, and fallback-to-blocked semantics
- **Orchestrator** — selects tasks (or records agent-selected tasks), drives
  workflows, manages sprint lifecycle, handles crash recovery, writes repo
  context projections and scaffold artifacts

---

## 2. Data Model

All tables live in a single SQLite database per engine instance. A project
points at one target repository. Multiple projects can coexist in one engine
database.

### 2.1 Projects

```sql
CREATE TABLE projects (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    repo_path       TEXT NOT NULL,
    spec_path       TEXT,                   -- path to spec (relative to repo or absolute)
    methodology     TEXT NOT NULL DEFAULT 'development',
    workflow_id     TEXT NOT NULL,
    default_branch  TEXT NOT NULL DEFAULT 'main',
    settings_json   TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
```

`settings_json` holds per-project configuration:

- `default_model`: model to use when a role doesn't specify one
  (e.g. `"claude-opus-4-6"`, `"claude-sonnet-4-6"`, `"gpt-5.4"`)
- `cost_limit_per_task_usd`: kill gate per task (sum of all runs)
- `cost_limit_per_sprint_usd`: alert/block gate per sprint
- `time_limit_per_run_minutes`: kill gate per individual agent run
- `task_selection_mode`: `"directed"` or `"autonomous"` (see §6.2)
- `context_dir`: where to write ephemeral context in the repo
  (default: `.foreman`)
- `test_command`: command for the `_builtin:run_tests` step
  (default: `"./venv/bin/python -m unittest discover -s tests"`)
- `max_step_visits`: max times a workflow step can be visited per task
  before auto-blocking (default: `5`)
- `max_infra_retries`: max infrastructure error retries per run
  (default: `3`)
- `event_retention_days`: how long to keep event rows; `null` = forever
  (default: `null`)
- `write_pr_summaries`: write completion summaries to `docs/prs/` on
  merge (default: `false`)
- `write_checkpoint_notes`: write checkpoint notes to `docs/checkpoints/`
  on sprint completion (default: `false`)

### 2.2 Sprints

```sql
CREATE TABLE sprints (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id),
    title           TEXT NOT NULL,
    goal            TEXT,
    status          TEXT NOT NULL DEFAULT 'planned',
        -- planned | active | completed | cancelled
    order_index     INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    started_at      TEXT,
    completed_at    TEXT
);
```

Only one sprint per project may be `active` at a time.

### 2.3 Tasks

```sql
CREATE TABLE tasks (
    id                      TEXT PRIMARY KEY,
    sprint_id               TEXT NOT NULL REFERENCES sprints(id),
    project_id              TEXT NOT NULL REFERENCES projects(id),
    title                   TEXT NOT NULL,
    description             TEXT,
    status                  TEXT NOT NULL DEFAULT 'todo',
        -- todo | in_progress | blocked | done | cancelled
    task_type               TEXT NOT NULL DEFAULT 'feature',
        -- feature | fix | refactor | docs | spike | chore
    priority                INTEGER NOT NULL DEFAULT 0,
    order_index             INTEGER NOT NULL DEFAULT 0,
    branch_name             TEXT,
    assigned_role           TEXT,
    acceptance_criteria     TEXT,
    blocked_reason          TEXT,
    created_by              TEXT NOT NULL DEFAULT 'human',
        -- 'human' | 'agent:<role_id>' | 'orchestrator'
    depends_on_task_ids     TEXT NOT NULL DEFAULT '[]',
    workflow_current_step   TEXT,        -- persisted for human gate resume
    workflow_carried_output TEXT,        -- persisted for human gate resume
    step_visit_counts       TEXT NOT NULL DEFAULT '{}',  -- JSON: {"develop": 3, "review": 2}
    created_at              TEXT NOT NULL,
    started_at              TEXT,
    completed_at            TEXT
);
```

Tasks can be created before a sprint starts (by a human or architect) or
during a sprint (by a developer via `signal.task_created`). Mid-sprint
tasks belong to the current sprint.

Dependency enforcement: tasks whose `depends_on_task_ids` contain
incomplete task IDs are skipped at selection time.

`workflow_current_step` and `workflow_carried_output` are written when a
human gate pauses the workflow, and read when the workflow resumes after
human approval (see §6.7).

`step_visit_counts` tracks how many times each workflow step has been
visited for this task, to enforce the max steering loop limit (see §6.8).

### 2.4 Runs

```sql
CREATE TABLE runs (
    id              TEXT PRIMARY KEY,
    task_id         TEXT NOT NULL REFERENCES tasks(id),
    project_id      TEXT NOT NULL REFERENCES projects(id),
    role_id         TEXT NOT NULL,
    workflow_step   TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
        -- pending | running | completed | failed | killed | timeout
    outcome         TEXT,
        -- approve | deny | steer | done | error | blocked
    outcome_detail  TEXT,
    agent_backend   TEXT NOT NULL,
    model           TEXT,
    session_id      TEXT,
    branch_name     TEXT,
    prompt_text     TEXT,
    cost_usd        REAL DEFAULT 0.0,
    token_count     INTEGER DEFAULT 0,
    duration_ms     INTEGER,
    retry_count     INTEGER DEFAULT 0,
    started_at      TEXT,
    completed_at    TEXT,
    created_at      TEXT NOT NULL
);
```

### 2.5 Events

```sql
CREATE TABLE events (
    id              TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES runs(id),
    task_id         TEXT NOT NULL,
    project_id      TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    role_id         TEXT,
    timestamp       TEXT NOT NULL,
    payload_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_events_run ON events(run_id, timestamp);
CREATE INDEX idx_events_project ON events(project_id, timestamp);
CREATE INDEX idx_events_type ON events(event_type, timestamp);
```

Event types:

**Agent lifecycle:**
- `agent.started` — process launched
- `agent.message` — text output; `{text, phase}`
- `agent.tool_use` — tool call; `{tool, input}`
- `agent.command` — shell command; `{command, cwd}`
- `agent.file_change` — file modified; `{tool, path}`
- `agent.cost_update` — cost snapshot; `{cumulative_usd, cumulative_tokens}`
- `agent.completed` — finished; `{session_id, cost_usd, duration_ms}`
- `agent.error` — agent-level error
- `agent.infra_error` — infrastructure error (API down, process crash)
- `agent.killed` — killed by gate; `{reason, gate_type}`

**Agent signals:**
- `signal.task_started` — `{title, task_type, branch, criteria}`
- `signal.task_created` — `{title, task_type, description, criteria}`
- `signal.progress` — `{message}`
- `signal.blocker` — `{message}`
- `signal.completion` — `{summary}`

**Workflow lifecycle:**
- `workflow.step_started` — `{step, visit_count}`
- `workflow.step_completed` — `{step, outcome}`
- `workflow.transition` — `{from_step, to_step, trigger}`
- `workflow.no_transition` — `{step, outcome}`
- `workflow.loop_limit` — `{step, visit_count, max_visits}`
- `workflow.paused` — `{step, reason}` (human gate)
- `workflow.resumed` — `{step, decision}`

**Gate triggers:**
- `gate.cost_exceeded` — `{limit_usd, actual_usd, scope}` (scope: "run" or "task")
- `gate.time_exceeded` — `{limit_minutes, actual_minutes}`

**Engine actions:**
- `engine.merge` — `{branch, target}`
- `engine.merge_failed` — `{branch, error}`
- `engine.context_write` — `{path}`
- `engine.scaffold_write` — `{files}`
- `engine.pr_summary_write` — `{path, branch}`
- `engine.checkpoint` — `{tag, sprint_id}`
- `engine.crash_recovery` — `{task_id, message}`
- `engine.test_run` — `{command, exit_code, output_tail}`
- `engine.event_pruned` — `{count, older_than}`

---

## 3. Role Configuration

Roles are TOML files under `roles/`. The engine ships defaults; users can
override or add custom roles.

### 3.1 Developer Role

```toml
# roles/developer.toml

[role]
id = "developer"
name = "Developer"
description = "Writes code, tests, and documentation for assigned tasks"

[agent]
backend = "claude_code"
model = ""                           # empty = project default
session_persistence = true
permission_mode = "bypassPermissions"

[agent.flags]
verbose = true

[agent.tools]
allowed = []
disallowed = []

[prompt]
# Available variables:
#   {task_title}, {task_description}, {task_type}, {acceptance_criteria}
#   {branch_name}, {sprint_context}, {project_status}
#   {repo_instructions}  — contents of AGENTS.md
#   {spec_path}          — path to the spec file for the agent to read
#   {completion_marker}, {previous_feedback}
#   {signal_format}
template = """
You are working on the following task:

## Task: {task_title}
Type: {task_type}
Branch: {branch_name}

### Description
{task_description}

### Acceptance Criteria
{acceptance_criteria}

### Sprint Context
{sprint_context}

### Project Status
{project_status}

### Repository Instructions
{repo_instructions}

### Project Spec
The full project specification is at: {spec_path}
Read it if you need to understand the broader product direction.

{previous_feedback}

### Structured Signals
{signal_format}

### Rules
- Work only on the branch `{branch_name}`
- Never merge to main — the supervisor handles merges after approval
- Use only ./venv/bin/python and ./venv/bin/pip for Python work
- Commit small, coherent changes with conventional prefixes
  (feat:, fix:, refactor:, test:, docs:, chore:)
- Create ADRs in docs/adr/ for meaningful architectural decisions
- Create or update docs/ARCHITECTURE.md and docs/ROADMAP.md when your
  work changes the codebase structure or project direction
- When the task is fully complete, run the test suite yourself to confirm
  all tests pass. The engine may also run tests independently after review.
  Write a structured completion summary and end your message with:
  `{completion_marker}`
- If you discover follow-up work, emit a TASK_CREATED signal
"""

[completion]
marker = "TASK_COMPLETE"
timeout_minutes = 60
max_cost_usd = 10.0

[completion.output]
extract_summary = true
extract_branch = true
```

### 3.2 Code Reviewer Role

```toml
# roles/code_reviewer.toml

[role]
id = "code_reviewer"
name = "Code Reviewer"
description = "Reviews completed work and returns APPROVE, DENY, or STEER"

[agent]
backend = "claude_code"
model = "claude-sonnet-4-6"
session_persistence = false
permission_mode = "bypassPermissions"

[agent.tools]
allowed = []
disallowed = ["Bash", "Write", "Edit", "NotebookEdit"]

[prompt]
template = """
You are reviewing completed development work.

## Task Under Review
{task_title}: {task_description}

### Acceptance Criteria
{acceptance_criteria}

### Developer Summary
{previous_output}

### Branch
{branch_name}

### Git Status
{git_status}

### Changed Files
{changed_files}

### Recent Commits
{recent_commits}

### Instructions
Use Read, Glob, and Grep to verify:
1. The claimed files exist and match the summary
2. Tests exist and are plausible
3. Relevant docs are updated if they exist (ARCHITECTURE.md, ADRs)
4. The work matches the acceptance criteria
5. No obvious regressions, leftover debug code, or hardcoded credentials
6. If an ADR should have been created for a significant decision, flag it

Return exactly one:
APPROVE
DENY: <reason>
STEER: <specific corrective action>
"""

[completion]
marker = ""
timeout_minutes = 10
max_cost_usd = 2.0

[completion.output]
extract_decision = true
```

### 3.3 Architect Role

```toml
# roles/architect.toml

[role]
id = "architect"
name = "Architect"
description = "Reads the spec and produces a task breakdown for a sprint"

[agent]
backend = "claude_code"
model = "claude-opus-4-6"
session_persistence = false
permission_mode = "bypassPermissions"

[agent.tools]
allowed = []
disallowed = ["Write", "Edit", "NotebookEdit"]

[prompt]
template = """
You are the architect for this project.

## Project Spec
The spec is at: {spec_path}
Read it thoroughly before producing your plan.

## Current State
{sprint_context}

{project_status}

## Instructions
Read the spec and the current repository state. Produce a task breakdown
for the next sprint as a JSON array. Each task object must have:

- "title": string
- "task_type": "feature" | "fix" | "refactor" | "docs" | "spike" | "chore"
- "description": string
- "acceptance_criteria": string
- "complexity": "small" | "medium" | "large"
- "depends_on": [list of task titles this depends on]

Output the array inside a ```json fenced block.

When done, end with: {completion_marker}
"""

[completion]
marker = "TASK_COMPLETE"
timeout_minutes = 15
max_cost_usd = 5.0

[completion.output]
extract_json = true
```

### 3.4 Security Reviewer Role

```toml
# roles/security_reviewer.toml

[role]
id = "security_reviewer"
name = "Security Reviewer"
description = "Checks for credential leaks, injection risks, dependency issues"

[agent]
backend = "claude_code"
model = "claude-sonnet-4-6"
session_persistence = false
permission_mode = "bypassPermissions"

[agent.tools]
allowed = []
disallowed = ["Bash", "Write", "Edit", "NotebookEdit"]

[prompt]
template = """
You are a security reviewer. Inspect the code changes on branch `{branch_name}`.

Check for:
- Hardcoded credentials, API keys, or secrets
- SQL injection or command injection risks
- Unsafe deserialization
- Dependencies with known vulnerabilities
- Overly permissive file or network access

### Changed Files
{changed_files}

Return exactly one:
APPROVE
DENY: <reason with specific file and line references>
"""

[completion]
marker = ""
timeout_minutes = 10
max_cost_usd = 2.0

[completion.output]
extract_decision = true
```

---

## 4. Structured Agent Signals

Agents can emit structured signals that the engine parses from their output.
Signals use a line-based marker format:

```
FOREMAN_SIGNAL: {"type": "task_started", "title": "Add claim store", "task_type": "feature", "branch": "feat/claim-store", "criteria": "Store persists and round-trips claims"}
FOREMAN_SIGNAL: {"type": "task_created", "title": "Add migration tooling", "task_type": "chore", "description": "...", "criteria": "..."}
FOREMAN_SIGNAL: {"type": "progress", "message": "Tests passing, writing docs"}
FOREMAN_SIGNAL: {"type": "blocker", "message": "Cannot resolve dependency conflict"}
```

The runner scans each output line for the `FOREMAN_SIGNAL:` prefix, parses
the JSON defensively (log and skip on failure), and emits `signal.*` events.

The `{signal_format}` prompt variable is replaced with documentation of
available signal types. In autonomous mode, `signal.task_started` is
required and must include `criteria` so the reviewer has something to
review against.

---

## 5. Workflow Definition

Workflows are directed step graphs in TOML. Each step runs a role or
built-in action. Edges fire on outcomes.

### 5.1 Standard Development Workflow

```toml
# workflows/development.toml

[workflow]
id = "development"
name = "Standard Development"
methodology = "development"

[[steps]]
id = "develop"
role = "developer"

[[steps]]
id = "review"
role = "code_reviewer"

[[steps]]
id = "test"
role = "_builtin:run_tests"

[[steps]]
id = "merge"
role = "_builtin:merge"

[[steps]]
id = "done"
role = "_builtin:mark_done"

[[transitions]]
from = "develop"
trigger = "completion:done"
to = "review"

[[transitions]]
from = "review"
trigger = "completion:approve"
to = "test"

[[transitions]]
from = "review"
trigger = "completion:deny"
to = "develop"
carry_output = true

[[transitions]]
from = "review"
trigger = "completion:steer"
to = "develop"
carry_output = true

[[transitions]]
from = "test"
trigger = "completion:success"
to = "merge"

[[transitions]]
from = "test"
trigger = "completion:failure"
to = "develop"
carry_output = true

[[transitions]]
from = "merge"
trigger = "completion:success"
to = "done"

[[transitions]]
from = "merge"
trigger = "completion:failure"
to = "develop"
carry_output = true

[[gates]]
trigger = "cost_exceeded"
action = "kill_and_block"
message = "Cost limit exceeded. Requires human review."

[[gates]]
trigger = "time_exceeded"
action = "kill_and_block"
message = "Time limit exceeded. Requires human review."

[fallback]
action = "block"
message = "Unhandled workflow outcome. Requires human review."
```

### 5.2 Architect-Led Development

```toml
# workflows/development_with_architect.toml

[workflow]
id = "development_with_architect"
name = "Architect-Led Development"
methodology = "development"

[[steps]]
id = "plan"
role = "architect"

[[steps]]
id = "human_approval"
role = "_builtin:human_gate"

[[steps]]
id = "develop"
role = "developer"

[[steps]]
id = "review"
role = "code_reviewer"

[[steps]]
id = "test"
role = "_builtin:run_tests"

[[steps]]
id = "merge"
role = "_builtin:merge"

[[steps]]
id = "done"
role = "_builtin:mark_done"

[[transitions]]
from = "plan"
trigger = "completion:done"
to = "human_approval"

[[transitions]]
from = "human_approval"
trigger = "completion:approve"
to = "develop"

[[transitions]]
from = "human_approval"
trigger = "completion:deny"
to = "plan"
carry_output = true

[[transitions]]
from = "develop"
trigger = "completion:done"
to = "review"

[[transitions]]
from = "review"
trigger = "completion:approve"
to = "test"

[[transitions]]
from = "review"
trigger = "completion:deny"
to = "develop"
carry_output = true

[[transitions]]
from = "review"
trigger = "completion:steer"
to = "develop"
carry_output = true

[[transitions]]
from = "test"
trigger = "completion:success"
to = "merge"

[[transitions]]
from = "test"
trigger = "completion:failure"
to = "develop"
carry_output = true

[[transitions]]
from = "merge"
trigger = "completion:success"
to = "done"

[[transitions]]
from = "merge"
trigger = "completion:failure"
to = "develop"
carry_output = true

[[gates]]
trigger = "cost_exceeded"
action = "kill_and_block"
message = "Cost limit exceeded."

[[gates]]
trigger = "time_exceeded"
action = "kill_and_block"
message = "Time limit exceeded."

[fallback]
action = "block"
message = "Unhandled workflow outcome."
```

### 5.3 Development with Security Review

```toml
# workflows/development_secure.toml

[workflow]
id = "development_secure"
name = "Development with Security Review"
methodology = "development"

[[steps]]
id = "develop"
role = "developer"

[[steps]]
id = "code_review"
role = "code_reviewer"

[[steps]]
id = "security_review"
role = "security_reviewer"

[[steps]]
id = "test"
role = "_builtin:run_tests"

[[steps]]
id = "merge"
role = "_builtin:merge"

[[steps]]
id = "done"
role = "_builtin:mark_done"

[[transitions]]
from = "develop"
trigger = "completion:done"
to = "code_review"

[[transitions]]
from = "code_review"
trigger = "completion:approve"
to = "security_review"

[[transitions]]
from = "code_review"
trigger = "completion:deny"
to = "develop"
carry_output = true

[[transitions]]
from = "code_review"
trigger = "completion:steer"
to = "develop"
carry_output = true

[[transitions]]
from = "security_review"
trigger = "completion:approve"
to = "test"

[[transitions]]
from = "security_review"
trigger = "completion:deny"
to = "develop"
carry_output = true

[[transitions]]
from = "test"
trigger = "completion:success"
to = "merge"

[[transitions]]
from = "test"
trigger = "completion:failure"
to = "develop"
carry_output = true

[[transitions]]
from = "merge"
trigger = "completion:success"
to = "done"

[[transitions]]
from = "merge"
trigger = "completion:failure"
to = "develop"
carry_output = true

[[gates]]
trigger = "cost_exceeded"
action = "kill_and_block"
message = "Cost limit exceeded."

[fallback]
action = "block"
message = "Unhandled workflow outcome."
```

### 5.4 Built-in Roles

| Role ID | Behavior |
|---|---|
| `_builtin:merge` | Merges the task branch to the project's default branch. Captures stderr on failure. If `write_pr_summaries` is enabled, writes the completion summary to `docs/prs/<branch-name>.md` and commits it as part of the merge. Outcome: `success` or `failure`. |
| `_builtin:mark_done` | Sets task status to `done`, records timestamps. Always `success`. Sprint completion, checkpoint tagging, and checkpoint notes are handled by the orchestrator's sprint lifecycle (see §6.4), not by this builtin. |
| `_builtin:human_gate` | Persists `workflow_current_step` and `workflow_carried_output` on the task, sets status to `blocked` with reason "Awaiting human approval", and returns control to the orchestrator. The orchestrator exits the inner workflow loop for this task and moves on. When a human issues `foreman approve <task-id>`, the orchestrator resumes from the persisted step. Outcome: `approve` or `deny`. |
| `_builtin:context_write` | Writes current sprint/task context into `{context_dir}/context.md` and project status into `{context_dir}/status.md`. Always `success`. Available for custom workflows that need explicit control over context timing; the orchestrator also writes context automatically before each agent run and after each task completes (see §6.5). |
| `_builtin:run_tests` | Runs the project's `test_command` in the repo. Captures exit code and last 200 lines of output. Outcome: `success` (exit 0) or `failure` (nonzero, with output tail as detail). |

---

## 6. Orchestrator

### 6.1 Main Loop

```
def run_project(project_id):
    project = load_project(project_id)
    workflow = load_workflow(project.workflow_id)
    recover_orphaned_tasks(project_id)

    # Resume any tasks paused at a human gate that have since been approved.
    # In Phase 1 at most one task can be paused (sequential execution), but
    # Phase 3 multi-project may produce several. Loop handles both cases.
    for resumed_task in find_approved_gate_tasks(project_id):
        run_workflow_from_step(project, workflow, resumed_task,
            step=resumed_task.workflow_current_step,
            carried_output=resumed_task.workflow_carried_output)
        resumed_task.workflow_current_step = None
        resumed_task.workflow_carried_output = None

    while True:
        task = select_next_task(project, workflow)
        if task is None:
            sprint = get_active_sprint(project_id)
            if sprint and all_tasks_resolved(sprint):
                complete_sprint(project, sprint)
                next_sprint = activate_next_sprint(project_id)
                if next_sprint is None:
                    break
                continue
            else:
                # Blocked tasks remain — cannot proceed
                break

        run_task(project, workflow, task)


def run_task(project, workflow, task):
    task.status = "in_progress"
    task.step_visit_counts = {}

    if project.task_selection_mode == "directed":
        if not task.branch_name:
            task.branch_name = generate_branch_name(task)
            create_branch(project.repo_path, task.branch_name)

    write_context(project, task)

    run_workflow_from_step(project, workflow, task,
        step=workflow.entry_step, carried_output=None)


def run_workflow_from_step(project, workflow, task, step, carried_output):
    current_step = step
    session_id = None

    while current_step is not None:
        # --- Check loop limit ---
        visit_counts = task.step_visit_counts
        visit_counts[current_step] = visit_counts.get(current_step, 0) + 1
        if visit_counts[current_step] > project.max_step_visits:
            emit_event("workflow.loop_limit",
                step=current_step,
                visit_count=visit_counts[current_step],
                max_visits=project.max_step_visits)
            task.status = "blocked"
            task.blocked_reason = (
                f"Step '{current_step}' visited {visit_counts[current_step]} times "
                f"(limit: {project.max_step_visits}). Stuck in a loop."
            )
            break

        # --- Check task-level cost gate ---
        task_cost = sum(r.cost_usd for r in get_runs(task_id=task.id))
        if project.cost_limit_per_task_usd and task_cost >= project.cost_limit_per_task_usd:
            emit_event("gate.cost_exceeded",
                limit_usd=project.cost_limit_per_task_usd,
                actual_usd=task_cost, scope="task")
            task.status = "blocked"
            task.blocked_reason = (
                f"Task cost ${task_cost:.2f} exceeds limit "
                f"${project.cost_limit_per_task_usd:.2f}"
            )
            break

        step_def = workflow.steps[current_step]
        emit_event("workflow.step_started",
            step=current_step, visit_count=visit_counts[current_step])

        if step_def.role == "_builtin:human_gate":
            # Persist state and exit the workflow loop
            task.workflow_current_step = current_step
            task.workflow_carried_output = carried_output
            task.status = "blocked"
            task.blocked_reason = "Awaiting human approval"
            emit_event("workflow.paused", step=current_step,
                reason="human_gate")
            return  # orchestrator moves on; resumes when human acts

        if step_def.role.startswith("_builtin:"):
            outcome, detail = execute_builtin(
                step_def.role, project, task, carried_output
            )
        else:
            role = load_role(step_def.role)
            prompt = render_prompt(
                role, project, task, carried_output, session_id
            )
            run = create_run(task, role, current_step, prompt)

            config = build_agent_config(role, project, run)
            if role.session_persistence and session_id:
                config.session_id = session_id

            for event in run_with_retry(config, project.max_infra_retries):
                store_event(run, event)
                check_agent_signals(event, task, project)

            update_run_from_result(run)
            if role.session_persistence:
                session_id = run.session_id

            outcome = run.outcome
            detail = run.outcome_detail

        emit_event("workflow.step_completed",
            step=current_step, outcome=outcome)

        transition = workflow.find_transition(current_step, outcome)
        if transition is None:
            emit_event("workflow.no_transition",
                step=current_step, outcome=outcome)
            task.status = "blocked"
            task.blocked_reason = (
                workflow.fallback.message
                if workflow.fallback
                else f"No transition for '{outcome}' at '{current_step}'"
            )
            current_step = None
        else:
            emit_event("workflow.transition",
                from_step=current_step,
                to_step=transition.to_step,
                trigger=transition.trigger)
            carried_output = detail if transition.carry_output else None
            current_step = transition.to_step

    write_context(project, task)
```

### 6.2 Task Selection: Directed vs Autonomous

**Directed mode (`"directed"`):**

The orchestrator picks the next `todo` task by priority, order, and
dependency satisfaction.

```
def select_next_task_directed(project):
    sprint = get_active_sprint(project.id)
    tasks = get_tasks(sprint_id=sprint.id, status="todo",
                      order_by="priority ASC, order_index ASC")
    for task in tasks:
        if dependencies_satisfied(task):
            return task
    return None
```

**Autonomous mode (`"autonomous"`):**

The orchestrator creates a placeholder task. The agent reads context,
decides what to work on, creates its own branch, and emits a
`signal.task_started` with title, type, branch, and acceptance criteria.
The engine updates the placeholder from the signal.

```
def select_next_task_autonomous(project):
    sprint = get_active_sprint(project.id)
    in_progress = get_tasks(sprint_id=sprint.id, status="in_progress")
    if in_progress:
        return in_progress[0]
    task = create_task(
        sprint_id=sprint.id,
        title="(agent-selected)",
        status="todo",
        created_by="orchestrator",
    )
    return task
```

In autonomous mode, **the orchestrator does not create a branch**. The
agent creates its own branch and reports it. If the agent fails to emit
`signal.task_started`, the placeholder remains and the reviewer reviews
against whatever the agent actually did — this is a degraded but
functional path.

```
def check_agent_signals(event, task, project):
    if event.event_type == "signal.task_started":
        p = event.payload
        task.title = p["title"]
        task.task_type = p.get("task_type", "feature")
        task.branch_name = p.get("branch", task.branch_name)
        task.acceptance_criteria = p.get("criteria", task.acceptance_criteria)
        save_task(task)
    elif event.event_type == "signal.task_created":
        p = event.payload
        sprint = get_active_sprint(project.id)
        create_task(
            sprint_id=sprint.id,
            title=p["title"],
            task_type=p.get("task_type", "feature"),
            description=p.get("description"),
            acceptance_criteria=p.get("criteria"),
            created_by=f"agent:{task.assigned_role}",
        )
```

### 6.3 Sprint Lifecycle

- On project start, the orchestrator activates the first `planned` sprint.
- A sprint completes when all its tasks are `done` or `cancelled`.
- `blocked` tasks prevent sprint completion — they must be unblocked or
  cancelled first.
- Mid-sprint tasks created by agents belong to the current sprint.
- After completion, the next `planned` sprint is activated, or the engine
  stops.

### 6.4 Sprint Completion Actions

When a sprint completes:
1. Sprint status set to `completed`, `completed_at` recorded.
2. Repo tagged: `checkpoint-YYYYMMDD-<sprint-slug>`.
3. If `write_checkpoint_notes` is enabled, a checkpoint note is written
   to `docs/checkpoints/<tag>.md` listing completed tasks,
   blocked/cancelled tasks, and follow-ups. The note is committed
   before the tag is created.
4. `engine.checkpoint` event emitted.

### 6.5 Context Projection

Before each agent run, the orchestrator writes two ephemeral files into
`{context_dir}/` (default `.foreman/`, gitignored). See §7.3 for
contents. These files are not tracked by git.

### 6.6 Crash Recovery

```
def recover_orphaned_tasks(project_id):
    orphaned = get_tasks(project_id=project_id, status="in_progress")
    for task in orphaned:
        # Skip tasks paused at a human gate — those are intentionally blocked
        if task.workflow_current_step is not None:
            continue
        active_runs = get_runs(task_id=task.id, status="running")
        for run in active_runs:
            run.status = "failed"
            run.outcome = "error"
            run.outcome_detail = "Engine crashed during run"
            emit_event("engine.crash_recovery",
                task_id=task.id, run_id=run.id)
        task.status = "todo"
        task.blocked_reason = None
        task.step_visit_counts = {}
        emit_event("engine.crash_recovery",
            task_id=task.id, message="Reset to todo after orphaned run")
```

### 6.7 Human Gate Resume

When a human issues `foreman approve <task-id>`:

1. Load the task. Verify status is `blocked` and
   `workflow_current_step` is not None.
2. Look up the transition from the persisted step with outcome `approve`.
3. Set task status back to `in_progress`.
4. Resume `run_workflow_from_step` at the transition's target step with
   the persisted `workflow_carried_output`.
5. Clear `workflow_current_step` and `workflow_carried_output`.
6. Emit `workflow.resumed` event.

When a human issues `foreman deny <task-id> --note "..."`:

Same flow, but the outcome is `deny`. The transition graph determines
where to go (typically back to the planning step with the note as
carried output).

### 6.8 Step Visit Limit

Each task tracks `step_visit_counts` as a JSON dict mapping step IDs to
visit counts. Before entering any step, the orchestrator checks:

```
if visit_counts[step] > project.max_step_visits:
    block task with loop limit message
```

Default `max_step_visits` is 5. This prevents infinite develop→review→deny
loops. When a task is blocked by this limit, the human can inspect the
run history, adjust the task or criteria, reset the visit counts via
`foreman task unblock`, and let the engine retry.

### 6.9 Infrastructure Error Retries

```
def run_with_retry(config, max_retries=3):
    for attempt in range(max_retries + 1):
        try:
            yield from agent_runner.run(config)
            return
        except InfrastructureError as e:
            if attempt == max_retries:
                yield AgentEvent("agent.error", payload={
                    "error": str(e),
                    "retries_exhausted": True,
                })
                return
            backoff = 2 ** attempt * 5
            yield AgentEvent("agent.infra_error", payload={
                "error": str(e),
                "retry_in_seconds": backoff,
                "attempt": attempt + 1,
            })
            time.sleep(backoff)
```

### 6.10 Event Pruning (optional)

If `event_retention_days` is set in project settings, the orchestrator
runs a pruning pass on startup:

```
def prune_old_events(project_id, retention_days):
    if retention_days is None:
        return
    cutoff = now() - timedelta(days=retention_days)
    count = delete_events(project_id=project_id, older_than=cutoff)
    if count > 0:
        emit_event("engine.event_pruned", count=count, older_than=cutoff)
```

Events for `blocked` or `in_progress` tasks are never pruned regardless
of age.

---

## 7. Repo Scaffold

When `foreman init` creates a project, the engine generates a minimal
scaffold in the target repo. The goal is to produce only files that earn
their place: `AGENTS.md` because agents read it by convention, a directory
for ADRs because agents create them, and the ephemeral context directory
because the engine writes to it at runtime.

Convention documentation (branching, testing, releases) lives inside
`AGENTS.md` rather than in separate files. Project state tracking lives
in the engine's SQLite database rather than in committed markdown.
Architecture, roadmap, and changelog files are created by agents when the
project reaches a point where they're useful, not generated as empty
skeletons by the engine.

### 7.1 Generated Files

| Path | Contents |
|---|---|
| `AGENTS.md` | Single instruction file for agents. Covers branching, commits, venv, testing, ADRs, signals, and constraints. Generated from a Jinja2 template. User can customize freely; the engine re-reads it before each run. |
| `docs/adr/` | Empty directory. Agents create ADRs here for significant architectural decisions. |
| `.foreman/` | Gitignored directory for ephemeral engine context. |
| `.gitignore` entry | `.foreman/` added if not present. |

### 7.2 Generated AGENTS.md Template

`AGENTS.md` is the single file that carries all agent instructions. It is
generated from `templates/agents_md.md.j2` with project-specific variables
and covers:

**Project identity:**
- Project name
- Spec file path (so the agent knows where to read the full spec)

**Branching conventions:**
- Branch prefixes: `feat/`, `fix/`, `refactor/`, `docs/`, `spike/`, `chore/`
- One branch per task
- Never work directly on the default branch
- The engine handles merges after reviewer approval

**Commit format:**
- Conventional prefixes: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`
- Small, coherent commits

**Environment:**
- Use `./venv/bin/python` and `./venv/bin/pip`
- Never use system Python

**Testing:**
- The project's test command (from project settings)
- Run tests before marking work complete

**Documentation expectations:**
- Create ADRs in `docs/adr/` for meaningful architectural decisions
- Create or update `docs/ARCHITECTURE.md` when the codebase structure
  changes significantly
- Create or update `docs/ROADMAP.md` when completing milestones that
  shift priorities
- Create `CHANGELOG.md` when the project reaches a maturity where
  tracking changes across sprints is useful
- These files are agent-created and agent-maintained; the engine does
  not generate or manage them

**Signal format:**
- Full documentation of `FOREMAN_SIGNAL` types (`task_started`,
  `task_created`, `progress`, `blocker`)
- When to emit each signal
- Required fields per signal type

**Completion protocol:**
- The completion marker string
- Required completion summary format

**Constraints:**
- Never merge to the default branch
- Never edit files under `.foreman/`
- Never bypass denied or approval-gated operations

The user owns `AGENTS.md` after generation. The engine does not overwrite
it on subsequent runs — it only reads it to inject as `{repo_instructions}`
in agent prompts.

### 7.3 Ephemeral Context (engine-written at runtime)

Before each agent run, the engine writes two files into `.foreman/`:

**`.foreman/context.md`** — Sprint-scoped context:
- Sprint title, goal, status
- All tasks with current status
- Current task highlighted with full description and criteria
- Carried feedback from prior runs

**`.foreman/status.md`** — Project-scoped context:
- All sprints with status (completed, active, planned)
- Summary of completed sprints (task count, key deliverables)
- Current sprint detail
- Blocked items and open decisions

These are ephemeral, gitignored, and never committed. The engine writes
them; agents read them for context.

### 7.4 Optional Repo Artifacts

These are off by default. Enable via project settings.

**PR summaries** (`write_pr_summaries = true`):
When `_builtin:merge` succeeds, it writes the developer's completion
summary to `docs/prs/<branch-name>.md` and commits it as part of the
merge. Creates `docs/prs/` if it doesn't exist. Useful when the repo
is browsed on GitHub by people without access to the engine's database.

**Checkpoint notes** (`write_checkpoint_notes = true`):
When a sprint completes (§6.4), the engine writes a checkpoint note to
`docs/checkpoints/<tag>.md` listing completed tasks, blocked/cancelled
tasks, and follow-ups. Creates `docs/checkpoints/` if it doesn't exist.
Commits the note before tagging. Useful for long-running projects where
repo-level milestone records have value beyond the engine's database.

---

## 8. Agent Runner

### 8.1 Interface

```python
@dataclass
class AgentRunConfig:
    backend: str                    # "claude_code" | "codex"
    model: str | None
    prompt: str
    working_dir: Path
    session_id: str | None
    permission_mode: str
    disallowed_tools: list[str]
    extra_flags: dict[str, Any]
    timeout_seconds: int
    max_cost_usd: float             # per-run limit

@dataclass
class AgentEvent:
    event_type: str
    timestamp: str
    payload: dict[str, Any]

class AgentRunner:
    def run(self, config: AgentRunConfig) -> Iterator[AgentEvent]:
        """Launch agent, yield events until completion or failure."""
        ...
```

### 8.2 Claude Code Backend

Launches `claude --print --verbose --output-format stream-json`.
Supported models: `claude-opus-4-6`, `claude-sonnet-4-6`.

Event mapping:

| Claude stream event | AgentEvent type |
|---|---|
| `assistant` → text block | `agent.message` |
| `assistant` → `tool_use` name=`Bash` | `agent.command` |
| `assistant` → `tool_use` name in {Read,Write,Edit,NotebookEdit} | `agent.file_change` |
| `assistant` → `tool_use` other | `agent.tool_use` |
| `result` `is_error=false` | `agent.completed` |
| `result` `is_error=true` | `agent.error` |
| Line matching `FOREMAN_SIGNAL: {...}` | `signal.*` |

Cost tracking: primary from `result.total_cost_usd`. Fallback: estimate
from last `agent.cost_update` if result event is missing (process killed).

Between events the runner checks time and per-run cost gates. If exceeded,
kills the process and emits `agent.killed`.

Unknown event types are logged as `agent.tool_use` with raw data. The
runner never crashes on unexpected stream shapes.

### 8.3 Codex Backend

Uses the JSON-RPC protocol. Maps Codex notifications to the same
`AgentEvent` types. Supported models: `gpt-5.4`, `o3`.

Tool-level approvals from Codex are handled by the runner based on the
role's tool config. Domain-level approvals are handled by the workflow.

### 8.4 Session Management

- **Session-persistent roles** (developer): runner accepts `session_id`,
  passes `--resume <id>` to Claude Code. Orchestrator stores the ID from
  the first run and reuses it for subsequent runs of the same role on the
  same task.
- **Non-persistent roles** (reviewers): fresh session per run. No
  `--resume`. Each review is independent.

When a developer is steered back, the repo is unchanged (reviewers are
read-only). The developer resumes with full conversation history plus
the reviewer's feedback as new input.

---

## 9. Event Queries for UI/CLI

### 9.1 Task Board

```sql
SELECT id, title, status, task_type, branch_name, assigned_role,
       priority, order_index, acceptance_criteria, blocked_reason,
       created_by, created_at, started_at, completed_at
FROM tasks
WHERE sprint_id = (
    SELECT id FROM sprints
    WHERE project_id = ? AND status = 'active'
)
ORDER BY
    CASE status
        WHEN 'in_progress' THEN 0
        WHEN 'blocked' THEN 1
        WHEN 'todo' THEN 2
        WHEN 'done' THEN 3
        WHEN 'cancelled' THEN 4
    END,
    priority ASC, order_index ASC;
```

### 9.2 Live Activity Feed

```sql
SELECT e.*, r.role_id, t.title as task_title
FROM events e
JOIN runs r ON e.run_id = r.id
JOIN tasks t ON e.task_id = t.id
WHERE e.project_id = ?
ORDER BY e.timestamp DESC
LIMIT 50;
```

### 9.3 Run History for a Task

```sql
SELECT id, role_id, workflow_step, status, outcome, outcome_detail,
       model, cost_usd, token_count, duration_ms, retry_count,
       started_at, completed_at
FROM runs
WHERE task_id = ?
ORDER BY created_at ASC;
```

### 9.4 Cost Tracking

```sql
-- Per task
SELECT t.id, t.title, COALESCE(SUM(r.cost_usd), 0) as total_cost
FROM tasks t LEFT JOIN runs r ON r.task_id = t.id
WHERE t.sprint_id = ?
GROUP BY t.id;

-- Per sprint
SELECT COALESCE(SUM(r.cost_usd), 0)
FROM runs r JOIN tasks t ON r.task_id = t.id
WHERE t.sprint_id = ?;

-- Per project
SELECT COALESCE(SUM(cost_usd), 0) FROM runs WHERE project_id = ?;
```

### 9.5 Agent Activity

```sql
-- Files touched
SELECT json_extract(payload_json, '$.path') as path
FROM events WHERE run_id = ? AND event_type = 'agent.file_change'
ORDER BY timestamp;

-- Commands run
SELECT json_extract(payload_json, '$.command') as command
FROM events WHERE run_id = ? AND event_type = 'agent.command'
ORDER BY timestamp;

-- Step visit counts for a task (to show loop history)
SELECT step_visit_counts FROM tasks WHERE id = ?;
```

---

## 10. CLI

```bash
# --- Project lifecycle ---
foreman init <repo-path> --name "My Project" --spec <spec-path> \
    --workflow development
foreman projects
foreman project <project-id>

# --- Sprint management ---
foreman sprint add <project-id> --title "Sprint 1" --goal "..."
foreman sprint activate <sprint-id>
foreman sprint list <project-id>
foreman sprint complete <sprint-id>

# --- Task management ---
foreman task add <project-id> --title "..." --type feature --criteria "..."
foreman task list <project-id>
foreman task block <task-id> --reason "needs design review"
foreman task unblock <task-id>           # also resets step_visit_counts
foreman task cancel <task-id>

# --- Running ---
foreman run <project-id>                 # autonomous loop
foreman run <project-id> --task <task-id> # single task

# --- Monitoring ---
foreman status                           # all projects overview
foreman board <project-id>               # kanban in terminal
foreman watch <project-id>               # live event tail
foreman watch --run <run-id>
foreman cost <project-id>
foreman cost <project-id> --sprint <sprint-id>
foreman history <task-id>                # all runs and events

# --- Human gates ---
foreman approve <task-id>
foreman approve <task-id> --note "looks good"
foreman deny <task-id> --note "rethink the approach"

# --- Configuration ---
foreman roles
foreman workflows
foreman config <project-id>
foreman config <project-id> --set cost_limit_per_task_usd=15.0
foreman config <project-id> --set max_step_visits=8
```

---

## 11. Directory Structure

```
foreman/
├── foreman/
│   ├── __init__.py
│   ├── models.py                 # dataclasses for all entities
│   ├── store.py                  # SQLite CRUD layer
│   ├── runner/
│   │   ├── __init__.py
│   │   ├── base.py               # AgentRunner protocol, AgentEvent, AgentRunConfig
│   │   ├── claude_code.py        # Claude Code stream-json backend
│   │   ├── codex.py              # Codex JSON-RPC backend (stub in Phase 1)
│   │   └── signals.py            # FOREMAN_SIGNAL line parser
│   ├── roles.py                  # TOML role loader, prompt template renderer
│   ├── workflows.py              # TOML workflow loader, transition resolver
│   ├── orchestrator.py           # Main loop, task selection, sprint lifecycle
│   ├── builtins.py               # merge, mark_done, human_gate, run_tests, context_write
│   ├── scaffold.py               # Repo scaffold generator (AGENTS.md, docs/, etc.)
│   ├── git.py                    # Branch, merge, tag, status, diff helpers
│   ├── context.py                # Sprint/task/status markdown projection
│   ├── cli.py                    # CLI entry point
│   └── errors.py                 # InfrastructureError, AgentError, etc.
├── roles/
│   ├── developer.toml
│   ├── code_reviewer.toml
│   ├── architect.toml
│   └── security_reviewer.toml
├── workflows/
│   ├── development.toml
│   ├── development_with_architect.toml
│   └── development_secure.toml
├── templates/
│   ├── agents_md.md.j2           # Jinja2 template for generated AGENTS.md
│   ├── checkpoint.md.j2          # template for checkpoint notes (used when write_checkpoint_notes enabled)
│   ├── pr_summary.md.j2          # template for PR summaries (used when write_pr_summaries enabled)
│   └── context.md.j2             # template for ephemeral sprint context projection
├── tests/
│   ├── test_store.py
│   ├── test_models.py
│   ├── test_roles.py
│   ├── test_workflows.py
│   ├── test_orchestrator.py
│   ├── test_runner_claude.py
│   ├── test_signals.py
│   ├── test_builtins.py
│   ├── test_scaffold.py
│   ├── test_context.py
│   └── test_git.py
├── pyproject.toml
└── README.md
```

---

## 12. Key Design Decisions

### 12.1 SQLite as structured state, markdown as projection
Two consumers (agents and UI), one source of truth (SQLite), two
projections (`.foreman/context.md` for sprint scope,
`.foreman/status.md` for project scope).

### 12.2 Roles and workflows are declarative TOML
Adding a role or changing a review chain never requires engine code
changes.

### 12.3 Dual task selection: directed and autonomous
Pre-planned sprints use directed mode. Open-ended development uses
autonomous mode with agent signals. Both produce identical structured
state.

### 12.4 Session persistence for developers, fresh for reviewers
Developers keep conversation context across steering loops. Reviewers
are independent and read-only.

### 12.5 Structured events as the universal observation layer
Every action is a queryable event. CLI, web UI, cost tracking, and
loop-limit enforcement all consume the same stream.

### 12.6 Infrastructure vs agent error separation
API failures retry with backoff. Agent errors flow through transitions.

### 12.7 Unmatched outcomes block the task
No silent termination. Blocked tasks surface for human review.

### 12.8 Step visit limits prevent infinite loops
Default 5 visits per step per task. Configurable per project. Blocks
with an explanatory message.

### 12.9 Task-level cost gates between steps
The orchestrator checks cumulative task cost before each step, not just
within a run. Prevents a second developer attempt from burning budget
after an expensive first attempt.

### 12.10 Context in gitignored path
`.foreman/` is ephemeral. No conflicts between engine writes and agent
commits.

### 12.11 Minimal repo scaffold, AGENTS.md carries the weight
`foreman init` generates only `AGENTS.md`, `docs/adr/`, and `.foreman/`.
All agent instructions — branching, commits, testing, ADRs, signals,
constraints — live in the single `AGENTS.md` file rather than spread
across many thin docs. Architecture, roadmap, changelog, and other
documentation files are created by agents when the project needs them,
not generated as empty skeletons. PR summaries and checkpoint notes are
optional and off by default; the engine's SQLite database is the primary
record of project history.

### 12.12 Spec as a file path, not injected content
The spec may be large. The engine passes `{spec_path}` to the agent,
which reads the file itself. This avoids context window pressure and
lets the agent decide how much of the spec to consume.

---

## 13. What This Does NOT Cover Yet

- **Web UI** (Phase 2): data model and events support it.
- **Multi-project parallelism** (Phase 3): data model supports it;
  orchestrator is sequential. Human gate persistence (§6.7) already
  supports the async pattern needed for multi-project — the orchestrator
  can park one project's gated task and work on another.
- **Research methodology** (Phase 4): separate workflow and role set.
- **Codex backend**: runner interface defined; implementation stubbed.
- **Architect → sprint automation**: architect proposes JSON tasks;
  human approves via `_builtin:human_gate`. Defensive parsing with
  fallback to blocked on failure.
