# Proposal: a method for the agents, how a repository is organised, and parallel work without collisions

- **Status:** proposal, for the owner to correct (roadmap stage 3, moved
  before stage 2 on 2026-11-24). Nothing here is built until it is
  corrected; an ADR follows, then the build through Foreman.
- **Date:** 2026-11-24
- **Written by:** Claude, from four surveys:
  - the methods already used in the company's projects;
  - published practice on agentic coding;
  - repository organisation;
  - parallel work.

  Their sources are listed at the end.

## Why

Sprint 62 was the first sprint run through Foreman. It showed what is
missing:
- **Shallow reviews.** Reviews approved in 5 to 15 seconds. The reviewer can
  only read files: it cannot run a test or open the page it judges.
- **Unchecked claims.** A layout was not checked at phone width, and an ADR
  number that did not exist was cited.
- **Collisions on shared files.** Every task edited the top of the same
  files (`CHANGELOG.md`, `docs/sprints/current.md`, the backlog), and they
  collided. One task took four develop passes for a one-minute change.
- **A stalled agent.** It ran a command that waits for input and sat for 18
  minutes.
- **An out-of-date prompt.** The reviewer's prompt still mentions a judge
  model removed on 2026-11-19.

The surveys agree on most of the remedies. Where they disagree, this
proposal says so and picks one, for the owner to confirm.

## What the evidence says, in short

- **A check that answers pass or fail, and evidence instead of claims.**
  Every vendor says it: a test, a build, a screenshot beside the design,
  with the command and its output shown. "All tests pass" alone says
  little (Anthropic, OpenAI, GitHub).
- **Agents grade their own work too kindly.** Anthropic: "out of the box,
  Claude is a poor QA agent". Same-model judges favour their own outputs,
  and sycophancy is common. What works:
  - a separate, sceptical reviewer that never saw the developer's
    reasoning;
  - checking against agreed criteria, one by one;
  - driving the running application as a user would.
- **Review is not free.** Review agents find about 40% of what people find,
  with false alarms. A false accusation can make an agent damage correct
  work. More rounds are not automatically better.
- **Agents cheat when tests and spec disagree.** In ImpossibleBench, GPT-5
  did so on 54% of the conflicting tasks. Two things cut it: making the
  tests read-only, and giving the agent a legitimate way to flag the task
  for a person. The flag alone took it from 54% to 9%. Hiding the tests
  stops cheating but lowers real performance.
- **Asking helps, but agents rarely ask unless told to.** Clarifying
  questions raised success on vague tasks by up to 74%.
- **Hard rules belong in the harness, not in stronger wording.** Prompts
  are guidance a model may skip. Hooks, sandboxes and gates are not.
- **Short instruction files.**
  - OpenAI keeps `AGENTS.md` to about 100 lines, as a table of contents.
    Anthropic says under about 200.
  - A 2026 study found long context files add over 20% to cost without
    raising success; they help only for practices the code does not show.
  - Add a rule when the same mistake happens twice.
- **Plan first only where the work is ambiguous.** Heavy spec frameworks
  (Spec Kit, Kiro, BMAD) are overkill for small tasks, and agents ignore
  parts of them (Thoughtworks).
- **Collisions in shared files are solved by layout, not care.**
  - No file that every change appends to: one file per entry, and the
    aggregate generated.
  - Identifiers that cannot clash.
  - The merged result tested before it lands, as merge queues do.
- **For several agents at once, splitting the work matters most.** Two
  agents on overlapping work do worse than one (CooperBench, Anthropic's C
  compiler). Locks on shared files throttle throughput (Cursor). Agents
  resolve real merge conflicts correctly only 50–60% of the time.

## What the company's projects already do well

Ideas to generalise:
- **orrery:**
  - a catalogue of invariants generated from the specs, each with a test;
  - a guard that fails a free-tier test that calls a paid model;
  - an escape log: each defect the owner found that the method missed
    records which check should have caught it, and the check is added;
  - a fixed list of review dimensions and severities;
  - fixes "by mechanism, not patched by symptom".
- **einstein_tiling:**
  - an agent may prepare a proposal but "may not authorize its own";
  - "an internal timeout alone is not a valid stop";
  - tests tiered by what they prove (unit, certificate, control,
    provenance).
- **The css project's corrections:**
  - never change established behaviour without calling it out;
  - state the cost of a fallback;
  - a screenshot proves some pixels changed, not that the change is right;
  - an invented detail in a design doc gets built as if decided.
- **Shared rules:** one branch per task, small commits, evidence with the
  commands and output, and secrets never logged.
- **Where the projects contradict each other:** how much documentation to
  write ("update a doc on every branch" against "no docs beyond what is
  asked"), commit style, and who decides technical questions.

## Part 1: the method the agents follow

### Principles

1. **Done is defined before code,** as acceptance criteria a check can
   decide: "When … the system …", the form Kiro calls EARS. A criterion that
   cannot be checked is rewritten or marked as a reviewer's judgement.
2. **Every change carries its evidence:** the commands run with their
   output, and for anything a user sees, a screenshot at the sizes that
   matter. A claim without evidence counts as not done.
3. **Three separate minds:**
   - whoever writes the acceptance checks is not the developer;
   - the reviewer is a fresh session that never saw the developer's
     reasoning;
   - none of them approves its own work.
4. **The harness enforces, the prompt explains.** Anything that must never
   happen is checked by Foreman:
   - protected tests;
   - files a role may not touch;
   - no interactive commands;
   - budgets.
5. **A legitimate way out.** "I cannot do this as specified" or "this is
   ambiguous" is a normal outcome. It raises a question for a person, with
   the options. It is never a reason to bend a test.
6. **Scope:** only what the task asks. A behaviour change outside it is
   called out and proposed, never bundled in. Follow-up work is filed as a
   task.
7. **Fixes by mechanism.** A defect someone finds after review is recorded
   with the check that should have caught it, and that check is added (the
   escape log).

### The steps

| Step | Who | What it produces | Enforced by Foreman |
|---|---|---|---|
| Plan, for tasks over a set size or marked unclear | a planner role | the acceptance criteria in checkable form; one check per criterion (a test or a script) marked protected; the files it expects to touch | the checks committed before development starts |
| Develop | the developer | the change, and a structured report: what changed, how each criterion was verified (command and output, screenshots), docs touched, risks, follow-ups | protected files unchanged; no interactive commands; time and cost caps |
| Test | Foreman | the project's checks (tiers later, direction 5) | already |
| Review | a reviewer in a fresh session | a verdict per criterion, with the evidence it checked. Severity on each finding; only real defects send the task back, and minor ones become notes or follow-ups | it can run the project's checks and open the application read-only (see open question 3); a cap on review rounds |
| Approve | a user, or Foreman by setting | the merge decision | already |

Small tasks (a wording fix, a one-line change) skip the plan step. Their
criteria come from the task as filed.

### What the developer reports

One structure, every time:
1. **What changed:** files and why, in a few lines.
2. **Each acceptance criterion:** how it was verified, with the command and
   its output, or the screenshot.
3. **What was not verified,** and why.
4. **Behaviour that changed** beyond the task, if any.
5. **Docs touched.**
6. **Follow-ups filed.**

### What the reviewer does

- Reads the criteria and the developer's report, then checks the evidence
  against the change.
- Runs the project's checks itself where it doubts them, and opens the page
  at the sizes that matter.
- Judges against the criteria, not style.
- Each finding has a severity:
  - S1–S2 send the task back;
  - S3–S4 become notes or follow-up tasks.

  This follows orrery's scale and the research on false accusations.
- Approves only with every criterion verified or explicitly marked as its
  own judgement.

### Operational safety, in the harness

Every agent command:
- runs with no input (`stdin` closed);
- runs with `GIT_EDITOR=true` and a no-op `EDITOR`;
- runs under a timeout.

The developer is told that interactive programs are not available and to
write a script instead (SWE-agent's practice).

## Part 2: how a project's repository is organised

The standard `foreman init` sets up, and Foreman itself follows:

```
README.md            for people: what it is, how to run it
AGENTS.md            for agents: a map of about 100 lines, the commands, the rules
                     the code does not show; nested AGENTS.md in a subsystem when useful
ARCHITECTURE.md      a short map of the code (what lives where); detail in docs/
CHANGELOG.md         generated from changes/ when a sprint finishes; never edited on a branch
changes/             one file per change: changes/<task key>.md
docs/
  spec/              the product spec (the owner's)
  adr/               decisions, one file each; numbered by Foreman at merge; index generated
  guide/             how-to and reference for users, one topic per file
  design/            UI reference, where the project has one
  directions/        the owner's long-term directions, one file each
```

**What leaves the repository's hand-edited files:**
- `docs/STATUS.md`, `docs/sprints/current.md` and `docs/sprints/backlog.md`:
  sprints, tasks, their status and the backlog live in Foreman's database.
  Where a readable copy is wanted, Foreman writes it when a sprint
  finishes. No task edits them.
- `docs/prs/<branch>.md`: the task's own record holds the same, and the
  merge commit carries a summary.
- Checkpoint notes: Foreman writes them when a sprint finishes (ADR-0036).

**Rules:**
- **A task's branch touches** the code, the tests, the docs its change
  affects, and new files of its own: a change file, an ADR. Never a shared
  log.
- **Big documents are split by topic.** For example `docs/MANUAL.md` (2,015
  lines) becomes `docs/guide/<topic>.md`, so two tasks rarely touch the same
  file.
- **`AGENTS.md` stays short.** It is partly generated by Foreman from the
  project's settings (commands, environment, the method) and partly written
  by people (what the code does not show). A rule is added when a mistake
  repeats, from the escape log.

## Part 3: parallel work without collisions

Most of these are cheap and follow from Part 2:
1. **No shared file that every change appends to:** change files, ADR files
   and generated indexes.
2. **Identifiers that cannot clash.**
   - Foreman owns the merge, so it gives an ADR its number at merge: the
     branch writes `docs/adr/new-<slug>.md`, and the merge renames it to
     the next number and regenerates the index.
   - Foreman also checks for duplicate numbers, which git never reports.
3. **Generated files are regenerated,** never merged by hand: lockfiles,
   indexes, the changelog.
4. **The merged result is what was tested.** ADR-0026 already brings a
   branch that is behind up to date and tests it again. With one task at a
   time (ADR-0039) there is no queue to manage.
5. **Small tasks:** one coherent change each.
6. **When several tasks run at once (later):**
   - the planner's expected files let Foreman avoid running two tasks on
     the same files or module at the same time. That is the biggest lever
     in the multi-agent evidence;
   - merges are ordered, each tested on top of the one before, as merge
     queues do;
   - a conflict an agent resolves goes back through test and review,
     because agents get them right only 50–60% of the time.

## Part 4: what Foreman builds, in order

Each item is a task once corrected; the order puts the cheapest and most
effective first.
1. **Non-interactive commands, in the harness:** closed `stdin`, editors set
   to no-op, timeouts.
2. **The developer's report structure and the reviewer's per-criterion
   verdict with severities.** Includes fixing the reviewer prompt's mention
   of a judge model that no longer exists.
3. **The reviewer can run the project's checks and open the application,
   read-only.** Depends on open question 3.
4. **Change files and a generated `CHANGELOG.md`,** gathered when a sprint
   finishes.
5. **ADR numbers given at merge, and a generated index.**
6. **Status, sprint and backlog copies generated by Foreman,** or retired;
   `docs/prs/` retired.
7. **The plan step:** a planner role, protected checks, and a merge refused
   if a protected check changed.
8. **The escape log:** a record of each defect a person found after review,
   with the check added.
9. **The generated `AGENTS.md` and the repository layout** in `foreman init`.
   Foreman's own repository and Assay move to it in steps: first the change
   files and the generated status, then the split of the manual and the
   architecture.

## What this proposal does not adopt, and why

- **A heavy spec framework** (Spec Kit, Kiro, BMAD) for every task: too much
  for small tasks. The plan step is used only above a size.
- **Long instruction files:** they cost more without raising success.
- **Hiding tests from the developer:** protected and visible instead. Hiding
  stops cheating but hurts the work.
- **Review rounds without a cap,** and send-backs for style: they damage
  correct work.
- **Locks on shared files for parallel agents:** they throttle throughput.
  Split the work instead.
- **`merge=union` for shared files:** it reorders, duplicates and brings
  back deleted lines.

## Open questions for the owner

1. **ADR identifiers:** a number given by Foreman at merge (keeps
   `ADR-0040`), or a date and slug (`20261124-slug`), which needs nothing
   from Foreman.
2. **Status, sprint and backlog files:** generated by Foreman when a sprint
   finishes, or retired with the dashboard as the only place.
3. **How the reviewer checks behaviour:**
   - option A: the reviewer itself may run the project's checks and open
     the application, in a sandbox that cannot change the branch;
   - option B: a separate verifier step does it and hands the reviewer its
     results.

   A is simpler. B keeps the reviewer purely a reader.
4. **When the plan step runs:** for tasks marked large, for every
   implementation task, or only when the person filing it asks.
5. **How much documentation a change writes.** The projects disagree.
   Proposed: only what its change affects, never a status or summary file.
6. **Who decides technical questions during a task.** Proposed, as orrery
   does: the agent decides and records it (an ADR when it constrains later
   work); product direction is always asked. Foreman's current rule ("write
   the conflict into STATUS before changing behaviour") would go.

## Sources

The surveys' main sources:
- **Agentic coding, official guidance:**
  - Anthropic, Claude Code best practices: https://code.claude.com/docs/en/best-practices
  - Anthropic, Building effective agents: https://www.anthropic.com/engineering/building-effective-agents
  - Anthropic, harness design for long-running apps: https://anthropic.com/engineering/harness-design-long-running-apps
  - Anthropic, effective harnesses for long-running agents: https://anthropic.com/engineering/effective-harnesses-for-long-running-agents
  - OpenAI, Codex best practices: https://learn.chatgpt.com/guides/best-practices
  - OpenAI, Harness engineering: https://openai.com/index/harness-engineering/
  - GitHub, Copilot coding agent: https://docs.github.com/en/copilot/responsible-use/copilot-coding-agent
  - agents.md: https://agents.md/
- **Agentic coding, research:**
  - ImpossibleBench: https://arxiv.org/html/2510.20270v1
  - Ambig-SWE: https://arxiv.org/abs/2502.13069
  - context files and cost: https://arxiv.org/abs/2602.11988
  - LLM judges favour their own outputs: https://arxiv.org/abs/2404.13076
  - a panel of judges: https://arxiv.org/abs/2404.18796
  - sycophancy: https://arxiv.org/abs/2310.13548
  - METR on passing but unmergeable PRs: https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/
  - SWE-agent's interface: https://swe-agent.com/latest/background/aci/
  - spec-driven tools reviewed by Thoughtworks: https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html
- **Repositories:**
  - Diátaxis: https://diataxis.fr/
  - matklad, ARCHITECTURE.md: https://matklad.github.io/2021/02/06/ARCHITECTURE.md.html
  - Nygard, ADRs: https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions
  - MADR: https://github.com/adr/madr
  - log4brains on ADR ids: https://thomvaill.github.io/log4brains/adr/adr/20201016-use-the-adr-slug-as-its-unique-id/
  - Keep a Changelog: https://keepachangelog.com/en/1.1.0/
  - towncrier: https://towncrier.readthedocs.io/
  - changesets: https://github.com/changesets/changesets
  - GitLab changelog trailers: https://docs.gitlab.com/user/project/changelogs/
- **Parallel work:**
  - GitHub merge queue: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue
  - GitLab merge trains: https://docs.gitlab.com/ci/pipelines/merge_trains/
  - Zuul gating: https://zuul-ci.org/docs/zuul/9.2.0/gating.html
  - Uber, keeping master green at scale (EuroSys 2019): https://doi.org/10.1145/3302424.3303970
  - Jane Street, never break the build: https://blog.janestreet.com/making-never-break-the-build-scale/
  - GitLab's changelog conflicts: https://about.gitlab.com/blog/solving-gitlabs-changelog-conflict-crisis/
  - git's union merge: https://git-scm.com/docs/gitattributes/2.43.0
  - Anthropic's C compiler with 16 agents: https://www.anthropic.com/engineering/building-c-compiler
  - Cursor, scaling agents: https://cursor.com/blog/scaling-agents
  - CooperBench: https://arxiv.org/abs/2601.13295
  - Brun et al., merge conflicts: https://homes.cs.washington.edu/~mernst/pubs/vc-conflicts-tse2013.pdf
- **The company's projects (methods to generalise):**
  - orrery: `CLAUDE.md`, `specs/60-infra-quality/601_evaluation_harness.md`, `tests/escapes.yaml`;
  - einstein_tiling: `CLAUDE.md`, `tests/TEST_TIERS.json`, `docs/research/admissions/README.md`;
  - css_scheduling_optimizer: `docs/qa/`;
  - assay: `AGENTS.md`.

Some recent preprints were read in abstract only. The surveys mark them.
