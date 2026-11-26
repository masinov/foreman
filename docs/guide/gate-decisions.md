# Gate decisions and the version they name

A person's decision at a human gate records what was in front of them
(`human_gate_decisions`, migration 35; `foreman/domain/gate_version.py`).

- **Merge approval**: the task branch's head commit and the default branch's
  head, at the decision.
- **Plan approval**: a fingerprint (sha256) of the task's description and
  criteria, and the run whose plan it was.

A request may name the version it saw: `foreman approve <task> --version
<commit or fingerprint>` (7 characters or more), or the `version` field of
`POST /api/tasks/<id>/approve`; the task page sends the `gate_version` it
showed. If it is no longer current the approval is refused (HTTP 409, code
`version_changed`, with `current`), and the page shows the new version. Without
a version the decision is recorded against the current one and the CLI says
which. A send-back is never refused for a changed version.

The Activity line reads "Approved at abc1234" (the run's commit), and
`foreman history` shows `at=<branch>, default <base>` or `plan=<fingerprint>`.
