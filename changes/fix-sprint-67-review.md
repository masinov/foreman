# Fixes from the independent review of sprint 67

- A review step that moved the task's branch and then pushed now has the branch put back; before, the push was reported and the branch stayed moved.
- `run_scope = "none"` refuses every Claude Code tool that runs a command (Bash, Monitor, PowerShell), not only Bash. The MANUAL now says what the review sandbox does not stop: an agent that sets out to push can still do so with your credentials, and on Codex the scope is not enforced.
- The manager's sessions, and the model check, are started with Claude Code's auto-memory off, as agents are. The MANUAL no longer says the setting keeps an agent from writing those files.
- A branch that changes while its task waits at the merge gate is tested and reviewed again and comes back to the gate, instead of being blocked for an unblock.
- A worker killed hard also ends the tools its agents started in sessions of their own (Claude Code runs each Bash command that way), and its guard processes are reaped.
- The systemd units are given the installer's `PATH`, so `claude` is found, and restart thirty seconds apart, so a worker killed hard gets back in once the dead one's lease runs out instead of systemd giving up.
- `scripts/review_screenshots.py` migrates its copy of the database, so a branch that adds a migration can be looked at.
- A skipped update over uncommitted work tells the developer once, and to commit that work rather than discard it.
- Reads before the first edit: a here-string (`<<<`) is not taken for a heredoc, and `open()` counts as a write only with a real write mode.
- The test that leaves an asyncio loop running is failed by name and the loop cleared, so the tests after it on the worker are not failed too.
