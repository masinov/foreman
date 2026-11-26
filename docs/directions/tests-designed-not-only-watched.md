# Tests that are designed, not only watched

- Date: owner, 2026-11-22 and 23; tiers 2026-11-24; survey 2026-11-24; 2026-11-25
- Moved from the hand-written `docs/sprints/backlog.md` on 2026-11-26 (FOR-70). The words below are as they were written; only a reference to another section is now a link.

**Tests that are designed, not only watched (owner, 2026-11-22 and
23).** Who decides what must be tested, how it runs, and whether the
requirement is met. The owner's examples:
- a test must exist for one function of a component;
- a test runs the app's full workflow through the interface and returns
  a screenshot of the end screen.
- **Today:**
  - Each project has one shell command (`test_command`). Foreman keeps
    its exit code, duration, commit and output. It does not know which
    tests ran: a count, a name or a failure is only in the printed text.
  - Nothing says what must be tested. A task's acceptance criteria come
    nearest, and a review checks them, not a test.
  - There is no tester role. Tests are written only if the developer
    decides to.
  - The Checks tab has an "Evidence files" section, but the server
    always sends it empty.
- **One place per project, a Tests view, with three parts:**
  - **What must be tested.** Written by a user, or proposed by the
    manager and accepted by a user (Foreman stores it). Each one has the
    behavior, its level (unit, component, or a journey through the
    interface) and what proves it, such as a passing test or a
    screenshot. It either blocks a merge or only advises.
  - **Suites, how tests run.** Kept in a TOML file in the project's
    repository, like CI configuration, so they stay in step with the
    code and an agent changes them through review. Each suite has:
    - its command and its report (JUnit XML is common to pytest,
      vitest, jest, Playwright and others);
    - what it needs (a journey starts the app, waits until it is ready,
      then drives a browser);
    - what it produces (results, screenshots);
    - when it runs: every task, tasks touching some files, before a
      merge, or on a schedule.
  - **Tiers, so a step does not wait for every test (owner,
    2026-11-24).** Today every task's test step runs the project's whole
    `test_command`, however small the change. The common practice:
    - at each step, only the tests the change can affect, picked by a
      tool that knows which tests run which code (coverage-based, such
      as pytest-testmon, or by the dependency graph, such as
      `vitest --changed` or Nx and Bazel "affected"). Groups kept by
      hand go stale and miss side effects;
    - before the merge, the whole suite, because `main` must always
      pass;
    - before a release or on a schedule, what is too slow for every
      merge (journeys through the interface).
    A suite then says which tier it belongs to, and the merge gate
    stays the full run.
  - **Coverage, each requirement against reality.** Whether a test
    exists, which one, its last result and its screenshot. A requirement
    with no test is a gap. Closing a gap is a task for a tester role,
    and the review checks that the test really proves the requirement.
- **On a task:**
  - the Checks tab shows the requirements the task touched and whether
    their tests passed;
  - the tests that failed come first, then the tests the task added or
    changed, then the full list, folded, with a search;
  - a test's own name and docstring say what it checks (a fact); a
    model's summary is a claim (ADR-0018);
  - a journey's screenshot fills Evidence files.
- **Over time, in the statistics view:** flaky, slow and skipped tests.
- **Survey before the ADR:**
  - Playwright and its reports;
  - how test tools and CI pick tests (pytest markers, vitest projects,
    "affected" in Nx or Bazel);
  - tools that track coverage against requirements;
  - whether the central server's workers run tests through an existing
    CI runner (see [releases and deployment through CI/CD](releases-and-deployment-through-ci-cd.md)).
- **Survey done (2026-11-24),** of the company's own projects and of established practice.
  - **The kinds of check these projects need:**
    - fast unit tests (pytest or unittest);
    - tests against services, such as Postgres, Redis, a time-series store, or a client's database reached over VPN;
    - optimizer quality against reference results (objective value, feasibility, solve time on a fixed set of cases), often comparing two branches;
    - model training and evaluation against a baseline metric, often on a GPU;
    - GPU-only jobs;
    - evaluation of LLM output, which is paid and varies from run to run;
    - a CAD plugin on Windows with a licence and real drawing files;
    - long exact-solver and certificate runs;
    - image builds;
    - browser flows (several frontends and no browser tests yet).

    Two projects already split their tests into tiers of their own: one into free tests on every commit and paid model tests on request, another into unit, certificate, control and provenance tiers with a `slow` marker. Results are scattered: no common place for metrics or objective values.
  - **Practice:**
    - **Selection is an optimisation allowed to miss.** The tools that pick tests from a change are bound to one language or to a build graph (pytest-testmon, `vitest --changed`, Nx, Bazel), or predict from history (Meta, Develocity). The full required set still runs at the merge gate, on the merged result.
    - **CI tiers:** a fast set on each change, the full required set at merge, and slow, end-to-end, model and performance checks after merge, nightly or before release.
    - **Machines:** a job states labels (OS, GPU, licence, interactive desktop), and a runner advertises them (GitHub, GitLab, Buildkite).
    - **Results:** JUnit XML for test cases; metrics checked against a pinned baseline with a tolerance (pytest-benchmark, asv, MLflow evaluation, Evidently); files kept as evidence (screenshots, transcripts).
    - **Who owns what:** the project defines what runs, in its repository; the platform decides what is required and where it runs (protected config, runner pools).
    - **Agent- or person-performed checks** are workflow steps that record a verdict with evidence. There is no standard yet.
  - **Conclusion (Claude, for the owner to decide):** a tier is not a subsystem of its own. It is a verification step in a declarative workflow, as review tiers already are (`development_tiered`), and its parts land with the stages that own them:
    - **which command a test step runs:** today always the project's one `test_command`;
    - **a rule by changed paths:** small, and possible now;
    - **results as counts, metrics with a baseline and files:** the evidence model, ADR-0018;
    - **the machine it needs:** stage 6, labels;
    - **an agent-run check:** a tester role, stage 3;
    - **per-run services:** stage 4;
    - **slow checks on the integrated `main`:** stage 8;
    - **the tests view:** stage 5, designed with the other views.

    Language-bound test selection stays inside a project's own command (pytest-testmon or `--changed`), never in Foreman.
  - **2026-11-25:** the "rule by changed paths" is now part of ADR-0041: a workflow route may test the changed path groups a project names, so a test tier becomes a route to a test step.
