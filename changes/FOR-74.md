Reads before the first edit are counted right

- A Codex command is counted once, not as both the command and its tool use.
- A `>` inside quotes is no longer a write, and a newline separates commands.
- A Python script that opens a file for writing, `git apply`, `mv`, `cp` and `rm` count as changes.
