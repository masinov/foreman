# One central Foreman server, with workers on other machines

- Date: 2026-11-18
- Moved from the hand-written `docs/sprints/backlog.md` on 2026-11-26 (FOR-70). The words below are as they were written; only a reference to another section is now a link.

**One central Foreman server, with workers on other machines.**
- A worker program on each machine connects out to the server, keeps a
  clone per project and a working copy per task, and runs agent and test
  steps there. It streams events back and pushes the task's branch.
- A project or step names a machine, or states requirements such as OS
  and installed software. A task stays on the machine that holds its
  agent session.
- The setting is multi-user and multi-project, and identity is needed.
- First case: a BricsCAD MCP server developed on a Windows machine.
