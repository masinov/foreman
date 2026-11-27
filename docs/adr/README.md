# ADRs

Architectural Decision Records for Foreman belong in this directory.

Create an ADR only when a decision becomes an active implementation constraint.
Do not create speculative ADRs before code depends on them.

## How to add a decision

1. Write it as `docs/adr/new-<slug>.md`, with the title line
   `# ADR-XXXX: <Title>` and a `- Status:` line (`accepted`, `proposed`,
   `superseded by ADR-NNNN`; a parenthesis after the word is a note and stays
   out of the index). Refer to it elsewhere by that path. Do not pick a number.
2. When the task merges, Foreman gives the file the next free number: it is
   renamed to `ADR-NNNN-<slug>.md`, its title line gets the number, references
   to the `new-<slug>.md` path are rewritten, and the index below is
   regenerated. All of it is in the merge commit; the branch is not changed.
3. Foreman refuses a merge that would leave two ADRs with the same number, and
   names the files.
4. Never edit the index below by hand. It is generated from each ADR's title and
   status; what stands above the marker line is kept. The folder is the project
   setting `adr_dir` (`docs/adr` by default).

Numbered files are `ADR-0001-short-title.md`.

<!-- foreman:adr-index - generated from each ADR's title and status; edit the ADRs, not this list -->

## Index

| ADR | Title | Status |
|---|---|---|
| ADR-0001 | Runner Session And Backend Contract | accepted |
| ADR-0002 | Dashboard Data-Access Boundary | accepted |
| ADR-0003 | Web UI And API Boundary | accepted |
| ADR-0004 | Dashboard Backend Framework | accepted |
| ADR-0005 | Schema Migration Strategy | accepted |
| ADR-0006 | Sprint Autonomy Levels And Agent Decision Gates | accepted |
| ADR-0007 | Sprint Planner Chat Session | superseded by ADR-0022 |
| ADR-0008 | Completion Truth Contract | accepted |
| ADR-0009 | Multi-Model Endpoints Via Role Environment | accepted |
| ADR-0010 | Tiered Review, LLM-Judged Evidence, and the Escalation Ladder | accepted |
| ADR-0011 | The Resident Engine And The Project Engine Lock | accepted |
| ADR-0012 | One git worktree per task, and the operator's checkout is off limits | accepted |
| ADR-0013 | Intake Endpoint And API Tokens | accepted |
| ADR-0014 | Autonomy As Policy | accepted |
| ADR-0015 | Durable Notification Delivery | accepted |
| ADR-0016 | Dashboard Browser-Origin Defence | accepted |
| ADR-0017 | Host-Level Settings Are Operator-Only | accepted |
| ADR-0018 | Completion Evidence Is Facts, Not A Score | accepted |
| ADR-0019 | The Dashboard API Is Versioned And Has One Error Shape | accepted |
| ADR-0020 | Dashboard Design v7 Is The UI Reference, And How The Frontend Is Built | accepted |
| ADR-0021 | The Backlog Is A Place, Not A Sprint | accepted |
| ADR-0022 | The Manager Proposes, A Person Confirms | accepted |
| ADR-0023 | Agent sandbox, first cut | accepted |
| ADR-0024 | A project's own roles and workflows live in the database | accepted |
| ADR-0025 | The engine finishes a sprint only in an autonomous project | accepted |
| ADR-0026 | A Branch Is Current Before It Is Merged | accepted |
| ADR-0027 | A workflow is sound before it is saved | accepted |
| ADR-0028 | Foreman starts backlog work, and acceptance is its permission | accepted |
| ADR-0029 | On a task page the side bar is the conversation with the task's agents | accepted |
| ADR-0030 | A task's answers are in plain sight, and More holds what is rare | accepted |
| ADR-0031 | A checkout on the default branch follows the merge | accepted |
| ADR-0032 | The backend is built in layers, and a test holds them | accepted |
| ADR-0033 | A note is for the developer | accepted |
| ADR-0034 | Outcome numbers | accepted |
| ADR-0035 | Tests Are Counted From JUnit Reports | accepted |
| ADR-0036 | A Finished Sprint Is Tagged | accepted |
| ADR-0037 | A Record Belongs To A Run, A Sprint Or The Project | accepted |
| ADR-0038 | A Step's Repository Facts Are Recorded When It Ends | accepted |
| ADR-0039 | The Engine Runs One Task at a Time | accepted |
| ADR-0040 | A Method For The Agents, And A Repository Without Shared Logs | accepted |
| ADR-0041 | Workflows Route On Facts, And Roles Declare What They Touch | accepted |
| ADR-0042 | A Role Returns Its Record In A Fenced Block | accepted |
| ADR-0043 | The Work Is Paused, Not The Engine | accepted |
| ADR-0044 | The Reviewer Runs In The Backend's Sandbox, In Its Own Clone | accepted |
