# ADR-0024: A project's own roles and workflows live in the database

- **Status:** accepted
- **Date:** 2026-11-16
- **Sprint:** 60

## Context

Roles and workflows are declarative TOML (spec, `AGENTS.md`). They were
loaded from one place only: the files inside the installed package
(`foreman/data/roles`, `foreman/data/workflows`). A project had nowhere to
put a role or a workflow of its own, although the settings page said "A
project can override any of them in its own repository". To change what a
reviewer may do, a person had to edit Foreman's own files, for every project
at once.

Two more things came out of explaining this to the owner on 2026-11-16:

- A tool name in a role file was passed to the agent program unchecked. The
  program ignores a name it does not know, so a misspelt name gave the agent
  a different tool set than the one written, silently.
- The dashboard showed roles and workflows and could not change them
  (ADR-0017 refused `backend` and `permission_mode` over HTTP, and the
  dashboard wrote the rest into the shipped file).

The owner chose (2026-11-16) to keep a project's definitions in Foreman's
database, not as files in the project's repository, and asked for them to be
editable from the dashboard.

## Decision

1. **A project's own role or workflow is TOML text in the database**
   (table `definitions`, migration 25), in the same format as the shipped
   files. One with a shipped id replaces the shipped definition for that
   project; one with a new id adds to them. The shipped files stay the
   defaults every project starts from, and are not written by Foreman.
2. **Every save is a revision.** The table is append-only: project, kind,
   id, revision, text, who, when. The highest revision is current; a
   revision marked removed means the project went back to the shipped
   definition. Nothing is edited in place, so what an agent was allowed to
   do at a given time can be answered.
3. **One loader.** `foreman.definitions.project_definitions(store,
   project_id)` returns what a project runs with. The engine loads it when a
   project's work starts (each pass, and when a gate decision is applied),
   so a change takes effect from the next task without a restart. The
   dashboard reads, the proposal card, the merge check and the CLI use the
   same function.
4. **A save is refused unless the whole set still loads.** A role change
   that leaves a workflow with an outcome its role cannot produce, a
   workflow that names a missing role, a role removed while a workflow names
   it, and the workflow a project uses being removed are all refused with
   the reason, before anything is stored.
5. **Tool names are checked.** For the Claude Code backend a role's
   `allowed` and `disallowed` lists may only hold names in
   `foreman.roles.CLAUDE_CODE_TOOLS`; anything else is refused when the role
   is loaded, shipped roles included. The backend name is checked too.
6. **Not in the repository, on purpose.** A definition kept as a committed
   file can be changed by a task's branch and arrive through a merge: an
   agent could loosen its own reviewer. In the database it is changed only
   by a person, through the CLI or the dashboard.
7. **Terminal:** `foreman role list|show|set --file|reset <project>` and the
   same for `foreman workflow`. A manager session may run `list` and `show`
   and is refused `set` and `reset` (ADR-0022).

## Amends ADR-0017

ADR-0017, decision 2, refused a role's `backend` and `permission_mode` over
HTTP because the one role file served every project and decided what an
agent may do on the host. With this ADR the dashboard edits a project's own
copy and never a shipped file. The owner's decision of 2026-11-16 is that a
person who can use the dashboard may edit a project's roles, tools and
prompt included. `PATCH /api/v1/roles/{id}`, which wrote into the shipped
file, is removed with the dashboard editor (the next slice).

What ADR-0017 protects is unchanged for settings: shell commands, paths and
the variables agents are given stay host-level and are not set over HTTP.

## Consequences

- A project can be given a stricter reviewer, another model per role, an
  extra step or a different order of steps without touching Foreman's code.
- Two projects can run different definitions under the same id.
- A definition stored today may stop loading after a Foreman upgrade that
  tightens the format. The engine then refuses to run that project and says
  which definition and why; `foreman role show` and `set` repair it.
- The list of known tools is tied to the agent program's version. A tool the
  program gains must be added to `CLAUDE_CODE_TOOLS` before a role can name
  it.
- Not done here: definitions do not travel with a clone of the repository;
  `foreman role show` and `set` are the way to copy one between machines.

## Amendment, 2026-11-16: the dashboard editor

- **Routes.** `GET /api/v1/projects/{id}/definitions` gives the project's
  roles and workflows as form fields and as text, with the words an editor
  chooses from (tools, decisions, models in use, what can do a step).
  `PUT /api/v1/projects/{id}/roles/{role}` and `.../workflows/{workflow}`
  save `{ "fields": ... }` from the form or `{ "text": ... }`, the TOML; a
  new definition also names `copy_of`. `DELETE` on the same paths drops the
  project's own text. `PATCH /api/v1/roles/{id}` is removed.
- **The form writes into the text it started from.** A role's flags, its
  signals and a workflow's cost and time gates are not in the form and are
  kept as they were. A test takes every shipped role and workflow through
  the form and back and compares.
- **An id is not changed by editing.** Saving text whose id differs from the
  one being edited is refused; a new definition is a copy saved under a new
  id.
- **A prompt must say how the run ends.** A role that decides must name each
  of its decisions in capitals in its prompt; a role that ends with a marker
  must name the marker or `{completion_marker}`. The engine reads the end of
  a run that way, and nothing joined the two before. Checked on every save
  (`check_role_says_how_to_end`).
- **No tool at all is said outright:** `[agent.tools] none = true`. An empty
  `allowed` list means every tool, and a deny list misses whatever it does
  not name: the two shipped reviewers that judge from what they are handed
  denied seven tools and still had the web tools and sub-agents. They now
  say `none = true`, which the Claude runner passes as `--tools ""` (checked
  with the installed CLI: it reports no tools).
- **Where it is in the dashboard:** Project settings has a Roles tab (the
  roles, a form per role, New role as a copy), and the Workflow tab has Edit
  steps and New workflow. Both editors have a text view.
