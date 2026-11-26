# ADR-0041: Workflows Route On Facts, And Roles Declare What They Touch

- **Status:** accepted (owner, 2026-11-25, in the conversation that settled
  the method proposal: "Agreed", on the facts a route may test, and "I agree
  with all of your suggestions")
- **Date:** 2026-11-25
- **Roadmap:** stage 3
- **With:** ADR-0040, the method that runs on this model
- **Extends:** ADR-0024 (a project's roles and workflows live in the
  database) and ADR-0027 (a workflow is sound before it is saved). The
  spec's §3 (roles), §5 (workflows) and §6.5 (context projection) are
  amended as each part lands.

## Context

The method in ADR-0040 needs a plan step that runs for some tasks and not
others; checks the developer cannot change; reports and verdicts with a
fixed structure; capped review rounds; and a question to a person from any
step. Fitting only the plan step would add one special case. The owner
asked instead what the workflow and role model would need for such things
to fit in general.

**What the model has today:**
- **Routes.** A route is a step plus that step's outcome, for example
  `triage` + `escalate` goes to `review`. A step can be reached only by a
  route.
- **What passes between steps.** Free text (`carry_output`).
- **Guards.** Each one is written in code, such as the completion-proof
  guard at merge. The limits a workflow declares are its cost and time
  gates. The project setting `max_step_visits` blocks a task stuck in a
  loop.
- **Waiting for a person.** Only `_builtin:human_gate`, with approve, deny
  or steer, where the workflow places it. An agent's only way to stop is
  `blocked`.
- **Roles.** A role lists its tools, its outcomes and a prompt template. A
  tool list cannot say "write tests, nothing else".
- **What the developer is given.** The prompt pastes the whole `AGENTS.md`
  (326 lines), the sprint's whole task list and every sprint since the
  start. Claude Code also loads `AGENTS.md` itself through `CLAUDE.md`, so
  it arrived twice (FOR-59's transcript). In FOR-50 to FOR-59 the developer
  made 2 to 10 reads before its first edit, all targeted, because the task
  descriptions named the files.

## Decision

### 1. Routes may depend on facts

A route may name facts that must all hold, as well as the outcome. Routes
from one step and outcome are tried in order, and the first whose facts
hold is taken. A route with no facts is the default, and every step and
outcome that has routes needs one.

The facts are a fixed list defined by Foreman, matched simply. A workflow
never contains a free expression: with fixed facts it can still be checked
before it runs (ADR-0027), and every route taken can be explained.

| Fact | Holds when | Example use |
|---|---|---|
| `label:<name>` | the task carries that label; labels are defined per project, and an undefined one fails validation | `unclear` → plan; `security` → security review |
| `no_criteria` | the task has no acceptance criteria | → plan, or a question to a person |
| `changed:<group>` | at least one changed path is in the group; path groups are named per project as path patterns | `frontend` → a screenshot check |
| `changed_only:<group>[,<group>]` | every changed path is in those groups | `docs` → skip the Python suite (a test tier) |
| `frozen_touched` | the change modified a file an earlier step froze | → refused, or a question to a person |
| `visits:<step>>=<n>` | the step has run at least n times for this task | review sent it back twice → ask a person, or a stronger reviewer |

The facts about a change exist only once a step has committed. A route
that tests them before Develop fails validation. A plan route is chosen
by a routing step that has no agent: `_builtin:route`, whose outcome is
`go`, so that its routes carry the facts.

Every route taken is recorded with the facts that chose it, and the
Activity shows them ("Took the plan route: no criteria").

### 2. Step results are records

A role declares the record it produces, with named fields. Records already
planned:
- the plan: criteria, checks and expected files;
- the developer's report (ADR-0040);
- the reviewer's verdict, per criterion, with findings and severities;
- a question to a person.

Foreman checks the shape and stores the record with the step's run. A
malformed record counts as an error outcome and is routed like one. Later
steps receive records as declared inputs (section 5), and the dashboard
shows them. Free text stays as the record's summary field.

### 3. Rules that hold across steps

A workflow may declare two rules. Foreman enforces both.
- **Freeze.** A step may freeze what it committed. A later change to those
  files makes `frozen_touched` true, and the merge refuses a branch where
  it holds, as it refuses one without completion proof.
- **Caps.** A step may set `max_visits`. Reaching it blocks the task with
  that reason. The project's `max_step_visits` stays as the overall stop.

### 4. A question to a person, from any step

`ask` becomes an outcome any agent role may declare:
- **The record:** the question, the options and a recommendation.
- **Waiting:** the task waits the way it waits at a gate, and holds the
  queue (ADR-0039).
- **The answer:** it goes back into the same step. The step resumes its
  session when the role keeps one, and otherwise receives the answer as an
  input.

The human gate's approve, deny and steer become one fixed question. The
question goes to the owner today, and to the task's responsible person
once stage 2 lands.

### 5. Roles declare what they touch, run, see and produce

- **Write scope.** The paths a role may change: `none`, a list of path
  patterns, or `all`. Frozen files are always excluded. Foreman checks the
  step's commits against the scope and refuses the step when they fall
  outside it, as it does for a branch violation. Examples: the planner
  writes tests only; a reviewer writes nothing.
- **Run scope.** Where a role may run commands:
  - `none`;
  - `sandbox`: a throwaway copy of the branch, discarded after the step. A
    reviewer runs the checks and opens the application there;
  - `branch`: the developer.
- **Inputs.** The role lists what it receives: the task, the criteria,
  named records of earlier steps, the change, the test results and the
  evidence. Its prompt template may use only those inputs. Another
  session's reasoning is never an input.
- **Output.** The record kind it produces (section 2) and its outcomes,
  as today.

### 6. What each step is given: three layers, pointers not contents

1. **The project.** It is the same for every step, so the prompt cache
   makes it cheap. It holds:
   - a short `AGENTS.md`, loaded once through the backend's own mechanism.
     Claude Code reads it through `CLAUDE.md`, and Codex reads it natively.
     Foreman no longer pastes it;
   - a short code map, `ARCHITECTURE.md` (ADR-0040).
2. **The task.** Where to start:
   - the criteria;
   - the expected files, with why each one matters;
   - the ADRs and spec sections that apply, by path and heading.

   The planner writes these, or the person or manager who files the task.
3. **The step.** The declared input records, such as the report, the
   findings and failing tests with file and line, and the change so far.

The sprint's whole task list and the project's sprint history leave the
developer's prompt. They remain an input a role may declare.

Agents still search the code themselves; the layers tell them where to
start. A generated code map, like Aider's repo map, is a later survey
(`docs/directions/code-map-for-agents.md`). The layers are judged by measurement: Foreman counts,
for each step, the reads before the first edit and the tokens used.

### 7. Existing definitions keep working

- A route without facts is today's route.
- A role without scopes keeps today's behaviour, where its tool list
  decides.
- A role that declares no record produces only its summary, as
  `carry_output` does today.

The built-in roles and workflows move to the new model as the build items
of ADR-0040 land.

## Consequences

- **The plan step needs no special case.** It is a planner role (write
  scope: tests; output: the plan record), a route on `no_criteria` or
  `label:unclear`, and a freeze on what it committed.
- **The same parts serve more than the plan step:**
  - test tiers, as routes on changed path groups (`docs/directions/tests-designed-not-only-watched.md`);
  - a security review only when sensitive paths change;
  - capped review rounds;
  - the legitimate way out (ADR-0040);
  - a reviewer that runs checks.
- **Validation grows** (ADR-0027). A workflow is refused when:
  - a route names an undefined label or path group;
  - a step and outcome have no default route;
  - a route tests the facts of a change before any step could commit;
  - a frozen file falls inside a later role's write scope without a route
    for `frozen_touched`.
- **Roles and workflows in the database (ADR-0024) gain fields.** Projects'
  own definitions are migrated with defaults that keep their behaviour.
- **The workflow format stays declarative.** If a need ever outgrows fixed
  facts, the answer is a new fact, or a deliberately limited real language.
  Expressions inside strings are not.
- **Not decided here:** the exact TOML syntax, and how a role's record is
  returned. That might be a fenced JSON block, or the backend's structured
  output. Each is settled with its build item, from the shapes above.
