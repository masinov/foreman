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

## Amendment (2026-11-26, owner: "The moving up the ladder must be configurable"): a step moves up its role's models only after failures of its own work

Decided with the owner on 2026-11-25 (`docs/directions/the-size-label-goes-and-a-step-moves-up-after-failures.md`),
built as FOR-71. It replaces the rule of ADR-0010, where a role's
`model_ladder` moved up one model on every visit to the step. A send-back
after a merge conflict, or a restart, climbed it too.

**What a role sets.** A workspace's default roles and a project's own roles
(ADR-0024) each say it, in the role's TOML and in the role editor:

- `[agent] model_ladder`: its models, cheapest first. One model never moves
  up. None means the project's default model.
- `[agent] escalate_after`: how many failures on one model before the next.
  At least 1, default 2, so the cheaper model gets another pass with the
  review's findings.

**What a task sets,** with the overrides that already exist
(`executor_overrides`): a model pinned for a step never moves up, and
`ladder_start` names the model of the ladder a step starts on, by the model
(a role that does not list it starts on its first). The size label may still
choose the first model until FOR-72 removes it.

**What counts as a failure of a step's own work:**

- its run ended without a result (an error, or no completion after the
  retry), whatever the step;
- the review sent the work back (deny or steer, which already need an S1 or
  S2 finding), counted against the step the workflow sends the work back to;
- the tests failed after it, counted against the step they send the work
  back to.

Not counted: an engine restart, a step cut by Stop (ADR-0043), a
send-back after a conflict or a branch brought up to date, a failed merge, a
wait for usage limits, an infrastructure error (git, the sandbox, the
network, a preflight), a limit the project set, a test run with no test
command, a person's send-back at a gate. Failures are kept on the task per
step and model (`tasks.step_failures`), so they survive a restart; a
person's unblock or reopen starts them over.

**The step's model** is the first model from where it starts whose failures
are fewer than `escalate_after`. Each move up is one line in the task's
Activity, "Develop moves up to claude-opus-5-5 · the review sent it back
twice", and the step's details say which model ran and whether it had moved
up. A run that ended without a result in a workflow with no route for that
outcome is run again on the next model rather than blocking, when its role
has more than one.

**Past the last model,** after `escalate_after` failures on it, the task
blocks for a person: "Develop failed twice on claude-opus-5-5, the last of
its models." A step with several models is limited by them, not by
`max_step_visits`; a role with one model keeps the loop limits.

**The session.** Both runners pass the model on every resume: Claude Code
starts `--resume <session> --model <model>`, and Codex sends `model` with its
`thread/resume`. A step that moves up therefore resumes its session on the
new model, and the new model sees what the earlier one did. When no session
exists for the role (it keeps none, or none ran yet) the step starts fresh
from its records: the task, the report, the findings.

`foreman outcomes` shows, per role and model, the steps, the failures of its
own work, the send-backs by review and the moves up to it, with the cost.
The word "escalate" stays the reviewer's ESCALATE signal; users read "moves up"
and "models".

## Amendment (2026-11-26, FOR-92; `docs/directions/assay-and-foreman.md`): a review says how it verified each criterion, and Foreman checks what it can

Section 2 says the reviewer's verdict is a record per criterion. A criterion
had a status and free-text evidence; nothing said whether the reviewer ran a
check, read the code or took the developer's report. An agent's word about
its own work is one line of evidence, and the developer's report repeated by
the reviewer adds nothing.

**Each criterion records its basis.** Three plain fields beside `criterion`,
`status` and `evidence` (records nest one level, ADR-0042): `ran` (a list of
the commands it ran for the criterion), `read` (a list of the files or parts
of the diff it read) and `from_report` (true when it relied on the
developer's report or the test step's output).

**Foreman checks what it can.** Each command under `ran` is looked for among
the `agent.command` events of the review: this run's, and those of the
earlier runs of the same session since the task's last other agent step (a
replay that resumes the session continues the same review, and is never
taken unchecked). A cited command counts only when each of its simple
commands ran as a whole simple command, program and arguments word for word;
option flags may differ, a `cd` before it, a pipe after it, a redirection and
a shell wrapper (`bash -lc '...'`) do not matter. Running one test file is not
running the suite, and `echo pytest x` or `grep 'pytest x'` is not `pytest x`.
One that was not run makes the verdict disagree with its outcome, as the other
verdict checks do, with the reason, and the step is replayed once. `read` is
the reviewer's word: every reviewer is given the diff, so a file of it read in
the prompt is read.

**What an approval needs is a property of the reviewer role,** in
`[completion.output]`, beside `approve_needs_reading`:

- `checked` (default): each criterion marked verified has a command it ran or
  a file it read; or is marked `judgement` with its reason in `evidence`. A
  criterion whose only basis is `from_report` is not verified.
- `ran`: each has a command it ran, or is marked `judgement` with its reason.
- `stated`: the reviewer's word, as before.

It is set where models are: the workspace's role is every project's default
and a project's own role overrides it (ADR-0024). There is no separate project
setting and no rule per task type. The role editor shows it only for a role
whose record is a `review_verdict`.

The reviewer's prompt says its own role's rule (`{approve_needs_rule}`), not
a list of the three. A role that cannot run a command (no tools, or a Claude
Code tool list without Bash) cannot ask for `ran`: it would never approve, so
it is refused when it loads. A reviewer role written before criteria had a
basis (its record declares no `ran`) is taken on its word, as `stated`.

*After an independent review (2026-11-27).* As first built, a replay that
resumed the session was not checked at all, and a cited command counted when
it appeared anywhere inside a recorded one; both let an approval through on a
command that never ran. Fixed in `fix/sprint-66-review`, with tests through
the engine.

## Amendment (2026-11-27, FOR-93; `docs/directions/assay-and-foreman.md`): a task names the documents it rests on, with the commit it named them at

Section 6's task layer says the ADRs and spec sections that apply are given
"by path and heading", and until now that was prose in the description:
nothing checked the path and nothing recorded which version the work was
planned against.

**A task names what it rests on.** It has a list of documents of the
repository: a path, and optionally a heading (`docs/adr/ADR-0041-....md`,
section 6; `docs/specs/engine-design-v3.md`, a section). For each, Foreman
records the commit of the project's default branch at the moment it was named.
The commit is captured, not typed. A document already on the list keeps its
commit when the list is edited, also when only its heading changes (a new
heading of a path already named takes that path's commit); only a new path is
stamped. The text form is `path` or `path#heading`; a space before the `#`
(`path #heading`, or `path #` with none) separates them when the path itself
has a `#`. A path and a heading are each one line.

**A path that is not a file on the default branch is refused,** with the
reason, wherever the list is set: the task form and page, `foreman task add`
and `foreman task edit`, `foreman backlog add`, a new sprint's first tasks
(the sprint is then not made either), the manager's proposals, the planning
prompt and the intake API (where the field `rests_on` is optional). A directory,
a symbolic link and a submodule are not files; a project whose repository is
not on the machine is refused with that reason. A manager's proposal checks
and stamps its documents when it is made, not when it is confirmed, so a merge
in between is reported to the task.

**Each agent step is given them in the task layer:** a section
"Documents this task rests on" with the path, the heading and the commit, as
pointers and not the text. It is added to every role's prompt, a project's own
templates included, unless the template places `{task_documents}` itself. The
task page's Overview lists them with their commits and opens each as it was at
that commit.

## Amendment (2026-11-27, FOR-94; `docs/directions/assay-and-foreman.md`): a task hears when a document it rests on changes

Assay's "stale binding" check, kept small. At each merge Foreman compares the
files the merge changed (the default branch before and after) with what each
unfinished task of the project rests on (in triage, todo, in progress or
blocked, wherever it is, the backlog included, and a paused task too; not done,
cancelled or declined; not the merging task). For each changed path that
matches, once per merge however many headings of it the task names:

- the task's Activity gets one line, a run of the engine's own records named
  "Document changed": "docs/adr/ADR-0041.md changed in FOR-80's merge (abc1234)
  since this task named it at def5678", with an `engine.document_changed`
  event holding both commits;
- the task page's "Rests on" says the document changed and opens the diff from
  the commit it was named at to the merge's;
- the task's next agent step has a section "Changed since this task was
  planned" in the task layer, naming the document, the merge and the commit it
  was named at.

**Nothing in the task is changed and it is not stopped.** Its description,
criteria and documents stay as they were; a person or the manager decides what
the change means for it (Assay: "Nothing downstream is edited automatically").
A person ends the notice by marking the document as read: "Mark as read at
<commit>" beside the changed document on the task page, or `foreman task edit
<task> --restamp PATH[#HEADING]`, stamps that entry with the default branch's
commit now (the notice belongs to the commit it was named at). Changing only
the heading keeps the commit, and so the notice.
A merge git cannot compare notes nothing: the merge is done whatever happens.

`foreman task list <project> --rests-on PATH[#HEADING]` lists every task that
rests on the document, finished ones and the backlog's included.
