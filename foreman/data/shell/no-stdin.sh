#!/bin/sh
# Runs one agent command with standard input on /dev/null (ADR-0040).
#
# Claude Code calls this as its shell prefix (CLAUDE_CODE_SHELL_PREFIX) and
# passes the whole command, its own shell setup included, as one argument.
# Without it, a command that holds a heredoc gets a socket as standard input,
# and anything in it that reads standard input waits until the Bash timeout.
# A heredoc inside the command still feeds its own program.
#
# The command was written for the shell Claude Code chose: zsh when that is
# the user's shell, bash otherwise.
shell=${CLAUDE_CODE_SHELL:-$SHELL}
case "$shell" in
  */bash|*/zsh) ;;
  *) shell=/bin/bash ;;
esac
exec "$shell" -c "$1" < /dev/null
