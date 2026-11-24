# ADR-0040: A Method For The Agents, And A Repository Without Shared Logs

- **Status:** accepted (owner, 2026-11-25: "I agree with all of your
  suggestions", after settling each open question of the proposal in turn)
- **Date:** 2026-11-25
- **Roadmap:** stage 3, moved before stage 2 on 2026-11-24
- **Evidence and reasoning:**
  `docs/proposals/2026-11-24-method-repository-parallel-work.md`, which
  holds the surveys, the sources and the alternatives not adopted.
- **With:** ADR-0041, the workflow and role model this method runs on.

## Context

Sprint 62 was the first sprint run through Foreman. It showed what is
missing:
- **Reviews too quick to mean much.** Reviews approved in 5 to 15 seconds.
  The reviewer can only read files, so it cannot run a test or open the
  page it judges.
- **Unchecked claims.** A layout was not checked at phone width, and an ADR
  number that did not exist was cited.
- **Collisions.** Every task edited the top of the same files and collided
  there: `CHANGELOG.md`, `docs/STATUS.md`, `docs/sprints/current.md` and the
  backlog. One one-minute change took four develop passes.
- **A stalled agent.** It ran a command that waited for input and sat for
  18 minutes.

The research agrees on most of the remedies:
- evidence instead of claims;
- a separate, sceptical reviewer;
- checks the developer cannot change;
- a legitimate way to say "I cannot do this as specified";
- short instruction files;
- no file that every change appends to.

The company's own projects already use several of these: orrery's escape
log and review severities, and einstein's rule that an agent may not
authorise its own proposals.

## Decision

### 1. The method

**Principles.**
1. **Done is defined before code,** as acceptance criteria a check can
   decide. A criterion that cannot be checked is rewritten, or marked as
   the reviewer's judgement.
2. **No evidence, not done.** Every change carries its evidence: the
   commands run with their output, and screenshots at the sizes that matter
   for anything a user sees.
3. **Three separate minds.**
   - Whoever writes the acceptance checks is not the developer.
   - The reviewer is a fresh session that never saw the developer's
     reasoning.
   - Nobody approves their own work.
4. **The harness enforces; the prompt explains.** Anything that must never
   happen is checked by Foreman, not asked for in a prompt.
5. **A legitimate way out.** "I cannot do this as specified" and "this is
   ambiguous" are normal outcomes. They become a question to a person
   (ADR-0041), never a reason to bend a test.
6. **Scope.** A change does only what the task asks. A behaviour change
   outside it is called out and proposed, not bundled in. Follow-up work is
   filed as a task.
7. **Fixes by mechanism.** A defect a person finds after review goes into
   the escape log, with the check that should have caught it, and that check
   is added.

**The steps of a development workflow.**

| Step | When | What it produces |
|---|---|---|
| Plan | when a route sends the task there (ADR-0041), e.g. no criteria or labelled unclear | checkable criteria, one check per criterion (frozen after this step), the expected files with why |
| Develop | always | the change, and the developer's report |
| Test | always | the project's checks, counted (ADR-0035) |
| Review | always | a verdict per criterion, with the evidence checked, and findings with a severity |
| Approve | as the project's policy says | the merge decision |

**The developer's report** always has the same parts:
1. what changed and why;
2. each criterion with how it was verified, as a command with its output or
   a screenshot;
3. what was not verified, and why;
4. any behaviour that changed beyond the task;
5. the docs touched;
6. the follow-ups filed.

**The reviewer:**
- checks the evidence against the change;
- runs the project's checks and opens the application itself where it
  doubts them, in a sandbox that cannot change the branch (ADR-0041, run
  scope);
- judges against the criteria, not against style.

Each finding carries a severity. S1 and S2 send the task back; S3 and S4
become notes or follow-up tasks. Review rounds are capped. The reviewer
approves only when every criterion is verified or marked as its own
judgement.

**Who decides during a task.** The agent decides technical questions
itself and records each decision: in an ADR when later work must follow
it, otherwise in its step's record. It asks a person when a decision:
1. changes what users see, and the spec, the design or the task does not
   settle it;
2. is hard to reverse: a storage engine, a public API, the shape of stored
   data, a file format;
3. adds an outside service or dependency, or costs money;
4. touches security, permissions or personal data;
5. contradicts the spec, the design or an accepted ADR.

Product direction is always the owner's, or later the responsible
person's. It covers anything a user would notice: which features exist and
how they behave, wording and look, scope and priority. A question to a
person comes with the options and a recommendation. This replaces the rule
"document the conflict in `docs/STATUS.md` before changing behaviour".

**Operational safety, in the harness.** Every agent command runs with
`stdin` closed, `GIT_EDITOR=true`, a no-op `EDITOR` and a timeout. The
developer is told that interactive programs are not available.

### 2. How a project's repository is laid out

`foreman init` sets this up, and Foreman's own repository follows it:

```
README.md         for people: what it is, how to run it
AGENTS.md         for agents: a short map (about 100 lines), the commands,
                  the rules the code does not show; partly generated
ARCHITECTURE.md   a short map of the code; detail lives in docs/
CHANGELOG.md      generated from changes/ when a sprint finishes
changes/          one file per change: changes/<task key>.md
docs/spec/        the product spec
docs/adr/         one file per decision, numbered at merge, index generated
docs/guide/       how-to and reference, one topic per file
docs/design/      the UI reference, where a project has one
docs/directions/  the owner's long-term directions, one file each
```

**What leaves hand-editing:**
- `docs/STATUS.md`, `docs/sprints/current.md` and `docs/sprints/backlog.md`.
  Their facts live in Foreman's database, and Foreman writes readable copies
  when a sprint finishes. No task edits them.
- `docs/prs/`. A task's own record holds the same, and the merge commit
  carries a summary.
- Checkpoint notes. Foreman writes them when a sprint finishes (ADR-0036).

**Documentation a change writes.** By default, only the docs related to
what it modified. Never a status or summary file.

**Documents are kept short.** `AGENTS.md` grows a rule only when a mistake
repeats, through the escape log. Big documents are split by topic, so two
tasks rarely touch the same file. `docs/MANUAL.md` (2,015 lines) and
`docs/ARCHITECTURE.md` (999 lines) are the first to split.

### 3. Parallel work without collisions

1. **No shared file that every change appends to.** Change files, ADR files
   and generated indexes replace them.
2. **Identifiers that cannot clash.** A branch writes its ADR as
   `docs/adr/new-<slug>.md`. The merge renames it to the next number,
   rewrites the branch's references to it, and regenerates the index.
   Foreman also refuses duplicate numbers, which git never reports.
3. **Generated files are regenerated,** never merged by hand.
4. **What lands is what was tested.** ADR-0026 already brings a branch that
   is behind up to date and tests it again.
5. **Small tasks.**
6. **When several tasks run at once (later; ADR-0039 keeps one at a time):**
   - tasks whose expected files overlap do not run together;
   - merges are ordered;
   - a conflict an agent resolves goes back through test and review.

### 4. Build order

Each item is a task through Foreman. The cheapest and most effective come
first.
1. **The harness:** non-interactive commands. Foreman stops pasting
   `AGENTS.md` into the prompt, since the backend already loads it
   (ADR-0041, context layers).
2. **Step records** (ADR-0041). The developer's report and the reviewer's
   per-criterion verdict with severities are the first records. This item
   also fixes the reviewer prompt's mention of a judge model, removed on
   2026-11-19. It also counts reads before the first edit, and tokens per
   step.
3. **Run scope.** The reviewer runs the checks and opens the application in
   a sandbox.
4. **Change files and a generated `CHANGELOG.md`.**
5. **ADR numbers given at merge,** with a generated index.
6. **Generated status, sprint and backlog copies.** `docs/prs/` is retired,
   and `scripts/validate_repo_memory.py` changes with it.
7. **Routes on facts, rules across steps, and the question to a person**
   (ADR-0041).
8. **Write scope, the planner role and frozen checks** (ADR-0041).
9. **The escape log.**
10. **The layout in `foreman init`,** with the generated part of
    `AGENTS.md` and a short `ARCHITECTURE.md`. Foreman's own repository and
    Assay move to it, and the manual is split.

## Consequences

- **The method arrives in pieces.** Until an item lands, the current rules
  in `AGENTS.md` still hold, including the PR note and the STATUS updates
  that `scripts/validate_repo_memory.py` checks. Each item changes
  `AGENTS.md` and the validator for its own part. No agent is told to
  follow a rule Foreman cannot yet support.
- **Fewer develop passes lost to collisions,** once items 4 to 6 land.
  These are the files that sent FOR-50 and FOR-52 back in sprint 62.
- **Steps cost a little more,** for the reviewer's checks and, on the routes
  that use it, the plan step. In exchange, fewer defects reach the owner,
  and send-backs over style stop.
- **`AGENTS.md` changes meaning.** It becomes a map, with rules that the
  escape log earns, not a manual.
- **Rejected,** with reasons in the proposal:
  - heavy spec frameworks for every task;
  - long instruction files;
  - tests hidden from the developer;
  - uncapped review rounds;
  - locks on shared files;
  - `merge=union`.
