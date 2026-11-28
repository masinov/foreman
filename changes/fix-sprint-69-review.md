# The independent review of sprint 69: questions, caps, labels and cited commands

- A step that asks a person is checked for the task's commits on the default branch before it waits, as every other step is: committing to `main` and then asking no longer slipped the task's work past the check.
- A person's answer reaches the step it answers even when the engine wrote a run in between (a Stop, a pause, crash recovery, a notice that a document changed), and is used once.
- Two answers sent at once record only one; the other is refused. A person's name keeps its case in what the agent is told; `foreman run --task` on a waiting task says to answer it; a chosen option on the task page is cleared by choosing it again.
- A review no longer gets credit for a command it only named: heredoc bodies are not commands, and `(` or `{` opens a group only where a command starts (not in a function's definition, an array, `echo (…)` or `echo { …; }`). A read that takes a `$( )` substitution is still a read.
- A step's cap keeps its resume point when it blocks a resumed task; only a block the cap made is taken for one when unblocking; a human gate takes no `max_visits`; a step that moves up its models gets room for those failures under its cap.
- Adding a task without labels never reads the project's settings; path patterns that would crash or never match (`[z-a]`, `./docs`, `docs//a`, `[[:alpha:]]`, `C:/x`) are refused when saved, and a trailing `/` matches a directory only, as in gitignore.
