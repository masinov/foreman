# ADR-0042: A Role Returns Its Record In A Fenced Block

- **Status:** accepted (ADR-0041 section 2 and the Sprint 63 task "A step's
  result is a record its role declares" ask for it; ADR-0041 left the form
  open, "a fenced JSON block, or the backend's structured output")
- **Date:** 2026-11-25
- **Sprint:** 63
- **Extends:** ADR-0041 section 2 (step results are records), ADR-0040 (the
  developer's report), ADR-0024 (a project's roles live in the database).
- **Number:** the usual next number for now; numbering happens at merge
  (ADR-0040).

## Context

A step's result passes to the next step as free text. ADR-0041 section 2
makes it a record the role declares: a kind and named fields. The record
must reach Foreman in a form it can parse reliably from both first-class
backends, Claude Code and Codex.

## Decision

### How the agent returns it: a fenced JSON block in the final message

The record is one JSON object in a fenced block whose info string is
`foreman-record`, in the agent's final message, before the completion
marker:

````
Words that summarise the work.

```foreman-record
{"summary": "...", "criteria": [...], ...}
```
TASK_COMPLETE
````

Chosen over the backend's structured output because:
- it works the same on both backends, through the one place Foreman already
  reads, the final message (`foreman/engine/output_contract.py`);
- a role's TOML stays the whole definition of the step, so a project's own
  role stored in the database (ADR-0024) can declare a record with no code;
- it needs no change to how a runner is launched, and a session that is
  resumed returns the record the same way.

The distinct info string keeps a record apart from any other JSON an agent
quotes. The last such block of the final message counts. The words around
the block stay the step's `outcome_detail` (the record's `summary` field
when there are none), so the free text keeps working for any later step that
carries it.

### How a role declares it

```toml
[completion.record]
kind = "developer_report"

[[completion.record.fields]]
name = "summary"
type = "text"
required = true
description = "What changed and why."
```

- `kind` and each field `name` are lowercase names. Every field says its
  `type` and `required`; `description` is optional and is shown to the agent.
- Types: `text` (required means not blank), `bool`, `text_list` (required
  means the key is present; an empty list says there is nothing to list) and
  `records`, a list of objects described by the field's own `fields`. A
  record's entries do not nest further.
- A field not declared is refused, so a typo is not stored.
- A role that returns a decision (a reviewer) cannot declare a record: the
  reviewer's verdict per criterion is its own record, a later task.
- The loader (`foreman/definitions/records.py`) refuses a malformed
  declaration with a message naming the role file, the field and what is
  wrong. The role's prompt takes `{record_format}`, which Foreman fills with
  the field list and an example block from the declaration, so the prompt and
  the check cannot drift apart.

### What Foreman does with it

1. **Check.** The final message is read after the marker check. A missing
   block, JSON that does not parse, or a record that breaks the declaration
   makes the step's outcome `error`. The detail starts "The step's record is
   not usable" and says what is wrong ("`criteria[1].verified` must be true or
   false"). It is routed as any error is.
2. **One correction.** As for a missing marker, the agent gets one corrective
   retry that resumes its session and says the shape again, before the error
   stands.
3. **Store.** A well-formed record is stored on the step's run in
   `runs.record_json` (migration 30) as `{"kind", "fields"}`. A run of a role
   with no record, and every earlier run, has none.
4. **Return.** `GET /tasks/{id}/runs` carries `record` on each run (the task
   detail's run list too).
5. **Hand on.** A later step receives the record as structured sections. A
   reviewer's prompt takes `{developer_report}`: the newest developer report
   of the task, criterion by criterion (`foreman/engine/report_words.py`); with
   none (a role that declares no record, or an older task) it is the
   developer's free text, as `{previous_output}` was.

### The developer's report

The shipped developer declares `developer_report` with the parts ADR-0040
lists: `summary` (what changed and why); `criteria`, one entry each with
`criterion`, `verification` (the command and its output, or a screenshot
path) and `verified`; `not_verified`; `beyond_task`; `docs_touched`;
`follow_ups`. The code, security, triage and frontier reviewers receive it
in their prompts. The task page shows it in the develop step's details.

## Consequences

- A role that declares no record behaves exactly as before, including a
  project's own roles in the database.
- A developer role copied into a project before this change keeps its old
  prompt and produces no record; its reviewers read its free text.
- The report is the developer's claim. Checking it against the change and
  the criteria is the reviewer's verdict (the next task), and the report's
  `criteria` entries are not yet compared with the task's own list.
- The block is text an agent writes, so a very long record is a long message.
  The agent's own output limit is the only bound for now.
