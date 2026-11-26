# Gate decisions and the version they name

A decision at a human gate records what was in front of the person, or of
the engine when the project's setting approves on its own
(`human_gate_decisions`, migration 35; `foreman/domain/gate_version.py`).

- **Merge approval**: the task branch's head commit and the default branch's
  head, at the decision.
- **Plan approval**: a fingerprint (sha256) of the task's description and
  criteria and of the run whose plan it was, and that run. The run is the
  last agent run of a step the gate is reached from (the step that wrote the
  plan); a person's decision, the engine's own records and built-in steps are
  never it. A plan redone by a new run with the same words is a new version.

## Naming the version

A request may name the version it saw: `foreman approve <task> --version
<commit or fingerprint>` (7 characters or more), or the `version` field of
`POST /api/tasks/<id>/approve`. The API gives it as `gate_version.token` on a
task, on each row of a sprint's tasks, and on Needs you's approval rows.

- Not current: refused, HTTP 409, code `version_changed`, with `current`.
- Not a version at all (fewer than 7 characters, not 0-9 a-f, or given at a
  gate with nothing to name, such as a branch whose head cannot be read):
  refused, HTTP 400, code `invalid_request`, field `version`, with the reason.
- None: the decision is recorded against the current version. The answer
  says which: "Approved FOR-51 (recorded at abc1234)"; with one named,
  "Approved FOR-51 at abc1234"; a plan's reads "plan abc1234".

A send-back is never refused for a changed version.

Every Approve on the dashboard names a version:

- **Task page**: the version the person is looking at. It is taken when the
  decision first shows for that stop at the gate, and from the diff's head
  when the person opens Changes; a background reload does not change it. The
  panel says "Approving abc1234". When a reload brings another version, the
  panel says the branch moved (or the plan changed) since, and "Look at ..."
  takes the new one and opens its diff (or the plan's output under Activity).
- **Needs you, the sprint's list and board**: the commit the row shows, the
  one its checks ran on, else the branch's head.

The manager's `approve_gate` proposal records the version at the gate when
it is proposed; confirming it is refused when the branch or plan changed
since.

## The merge lands what was approved

When the merge step is reached from a merge approval that recorded the
branch's head, and the branch has moved since, nothing is merged: the task
goes back to the gate, blocked with "The branch moved after it was approved:
approved at abc1234, it is now at def5678" (`engine.merge_blocked`, reason
`moved_after_approval`). Approving the new head lets the merge go on.

## Where it is shown

The task's Activity row says "Approved" with the commit in its commit
column, or "Approved, version not named" when the request named none (the
commit on hover). Elsewhere it reads "Approved at abc1234" or "Approved
(recorded at abc1234)". `foreman history` shows `at=<branch>, default <base>`
or `plan=<fingerprint> run=<run>`, with "(not named)" when none was named.
