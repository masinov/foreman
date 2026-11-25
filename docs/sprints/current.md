# Current Sprint

## Sprint 63 — the method, first part

- **Opened:** 2026-11-25 (owner: "Go ahead, but i want it to run fully
  autonomously and come back tomorrow to check. No supervision on my
  side.")
- **Status:** completed by Foreman (2026-11-25 01:34); reviewed afterwards by
  Claude with three independent reviewers, and fixed by hand before the new
  code went live (below)
- **Method:** through Foreman, unsupervised. Merges are approved by
  Foreman (`merge_approval = auto`) and the sprint is finished by Foreman
  (`sprint_completion = auto`) for this sprint. Claude keeps a watchdog,
  which steps in only for faults: a blocked task, a stopped engine, or a red
  CI run. The owner checks on 2026-11-26.

### Goal

The first build items of ADR-0040, on the model of ADR-0041:
- agent commands never wait for input;
- `AGENTS.md` reaches the agent once;
- a step's result is a record its role declares;
- the reviewer judges each criterion and gives severities;
- each step shows how much it read before its first edit;
- the code reviewer can run the checks and look at the page.

### Constraints

- ADR-0040 and ADR-0041 for what is built, the spec for behaviour, the
  design in `docs/design/dashboard-v7/` for the pages (ADR-0020), and
  ADR-0032 for where code goes.
- Until each ADR-0040 item lands, the rules in `AGENTS.md` still hold.
- One task at a time (ADR-0039).

### Tasks

| Key | Task | Depends on | Status |
|-----|------|------------|--------|
| FOR-60 | Agent commands never wait for input, and `AGENTS.md` reaches the agent once | none | done |
| FOR-61 | A step's result is a record its role declares, starting with the developer's report | none | done |
| FOR-62 | The reviewer's verdict is a record per criterion, and only serious findings send work back | FOR-61 | done |
| FOR-63 | A step's details show the reads before its first edit and the tokens it used | none | done |
| FOR-64 | The code reviewer runs the checks and takes screenshots in a sandbox | FOR-62 | done |

The full description and acceptance criteria of each task are in Foreman.

### Found during the run

- **2026-11-25 01:10, CI red on FOR-61's merge** (`310496e`): a duplicate
  `import json` in `tests/engine_support.py` failed `ruff`. Foreman's test
  step never ran the linters, so the merge went through. Fixed by hand
  (`fix/tests-duplicate-json-import`). By mechanism: Foreman's
  `test_command` now starts with `ruff check foreman tests scripts` and
  `lint-imports`, as CI does.

- **01:34, the sprint finished in 45 minutes.** Every code review had
  approved in about six seconds: the engine ran the code from before the
  sprint, so these tasks were reviewed the old way. Claude ran the checks
  (ruff, layers, 1,756 Python and 547 frontend tests, CI) and had each task
  reviewed against its criteria by an independent reviewer. Findings and
  what was done with them:
  - **FOR-64, the sandbox** (`fix/sandbox-git-and-prune`):
    - every git command failed in a sandbox on git 2.25 because of the
      push block's config format; fixed, with a test;
    - `foreman worktree prune` deleted a running review's sandbox; it now
      keeps a live task's sandbox;
    - the reviewer could not take screenshots on this machine. A reviewer
      that could not see a page had to mark it `not_verified`, which FOR-62's
      rule refuses on an approval, so every frontend task would have
      blocked. The reviewer now follows the project's own preview recipe
      (`scripts/review_screenshots.py`, in `AGENTS.md`), and judges from the
      code with an S3 finding when it cannot see the page. The worktree
      setup installs the `e2e` extra (a project setting).

  - **FOR-61 and FOR-62, the records** (`fix/records-robustness`, the
    ADR-0042 amendment of 2026-11-25):
    - a quoted block after the record replaced it;
    - the missing-marker retry did not ask for the record, so a task that
      used to recover would block;
    - an approval could list no criteria;
    - a developer who was sent back did not get the findings;
    - a lowercase severity spent the correction;
    - the example showed an S1;
    - another shape of report could break the prompts.

    All of these are fixed, with tests.

### Left for later

The rest of ADR-0040's build order:
- change files and a generated changelog;
- ADR numbers given at merge;
- generated status files;
- routes on facts, rules across steps, and the question to a person;
- write scope and the planner;
- the escape log;
- the layout in `foreman init`.

## Before this sprint

Sprint 62, "finish what's there", was completed on 2026-11-24:
`docs/sprints/archive/sprint-62-finish-whats-there.md`. Its ten tasks,
FOR-50 to FOR-59, ran through Foreman. On 2026-11-24 the roadmap put
stage 3 (a method for the agents) before stage 2. The proposal and ADRs
0040 and 0041 followed on 2026-11-25.
