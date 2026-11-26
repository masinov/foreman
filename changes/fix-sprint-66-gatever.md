# Every approval names the version it was given on, and the merge lands only that

- Every Approve on the dashboard names a version: Needs you, the sprint's list and board send the commit the row shows; the task page sends the version the person is looking at ("Approving abc1234"), kept while the page reloads, taken from the diff when Changes is opened, and says when the branch moved or the plan changed since, with "Look at ..." to take the new one.
- The merge step refuses a branch that moved after its approval: the task goes back to the gate, blocked with "The branch moved after it was approved".
- A plan's version is the run that wrote it as well as its text, so a redone plan is a new version; the run is the last agent run of the step before the gate.
- The manager's approval proposals record the version when proposed; a confirmation after the branch or plan changed is refused.
- A malformed version (too short, not hexadecimal, or at a gate with nothing to name) is a 400 with the reason. An approval that named no version says what it was recorded against: "Approved FOR-51 (recorded at abc1234)". The Activity row no longer repeats the commit of its commit column.
- Engine automatic approvals carry the version on their `workflow.gate_auto_approved` record. See `docs/guide/gate-decisions.md`.
