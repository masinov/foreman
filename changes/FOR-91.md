A worker killed hard leaves no agent behind, and a supervisor restarts it

- A worker killed with SIGKILL (or by the out-of-memory killer) no longer leaves an agent's tools running: a guard per agent group kills the whole group when the worker is gone.
- Systemd user units for the worker (`foreman-worker@<project>`) and the dashboard ship in `deploy/systemd/`, start at boot and restart after a crash; the MANUAL (6.2) gives the install commands. Installing is the operator's step.
- Tests: a hard-killed worker leaves no agent or tool of its agent; a restarted worker takes over from a crashed one and resumes its task.
