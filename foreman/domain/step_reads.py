"""Reads before a step's first change (ADR-0041 section 6).

``reads_before_first_change`` is the one place the rules live: given a run's
stored tool events in order, it says how many reading tool calls came before
the first change, and whether there was a change at all. Nothing here reads
the database or git.

Reading: ``Read``, ``Grep`` and ``Glob``; a shell command that only reads
(``cat``, ``sed -n``, ``rg``, ``grep``, ``ls``, ``find``, ``head``, ``tail``,
``wc``, ``git log``, ``git show``, ``git diff``, ``git status``, ``git grep``).
A change: ``Edit``, ``Write``, ``MultiEdit``, ``NotebookEdit`` or
``apply_patch``; a shell command that writes a file (a redirect into a file,
``sed -i``, ``perl -i``, a heredoc into a file, ``tee``); ``git commit``, ``git apply``, ``mv``, ``cp``, ``rm``, a Python script (a
heredoc or ``-c``) that opens a file for writing. A ``>`` inside quotes is not
a redirect, a newline separates commands, and a heredoc's body is not a command.
Any other call is neither.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

#: The event recorded when an agent run ends.
STEP_READS_EVENT = "engine.step_reads"

READ_TOOLS = frozenset({"Read", "Grep", "Glob"})
CHANGE_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch", "codex.fileChange", "fileChange"})

_READ_COMMANDS = frozenset({"cat", "rg", "grep", "ls", "find", "head", "tail", "wc"})
_READ_GIT = frozenset({"log", "show", "diff", "status", "grep"})
#: Commands that read and write nothing of the repository; they do not make a line a non-read.
_NEUTRAL = frozenset({"cd", "pushd", "popd", "set", "export", "true"})
# A redirect into a file; ``2>&1``, ``>&2`` and ``/dev/null`` are not one.
_REDIRECT = re.compile(r"(?:^|[^<>&\d])\d?>>?(?!&)\s*(?!/dev/null\b)[^\s&|;>]")
# ``<<<`` is a here-string, not a heredoc: no lines follow it.
_HEREDOC_TO_FILE = re.compile(r"(?<!<)<<(?!<)-?\s*['\"]?\w+['\"]?[^\n]*>")
_HEREDOC_START = re.compile(r"(?<!<)<<(?!<)-?\s*['\"]?(\w+)['\"]?")
_FILE_COMMANDS = frozenset({"mv", "cp", "rm"})
_GIT_CHANGES = frozenset({"commit", "apply", "mv", "rm"})
_GIT_APPLY_READ_ONLY = frozenset({"--check", "--stat", "--numstat", "--summary"})
# A Python script that writes: open(p, 'w'), Path.write_text, shutil or os file operations.
_PY_WRITE = re.compile(
    # The mode is open's own argument (a call inside the path is skipped
    # whole) and a real mode string, not any string with a w, a, x or + in it.
    r"open\((?:[^()]|\([^()]*\))*?,\s*(?:mode\s*=\s*)?['\"](?=[rbt]*[wax+])[rwxabt+]{1,4}['\"]"
    r"|\.write_(?:text|bytes)\(|shutil\.(?:copy|move|rmtree)|os\.(?:remove|unlink|rename|replace)\("
)
_SHELL_WRAP = re.compile(r"^(?:/\S*/)?(?:ba|z)?sh\s+-l?c\s+(.+)$", re.DOTALL)


@dataclass(frozen=True, slots=True)
class StepReads:
    """How many reads a run made before its first change; ``edited`` is False when it made none."""

    reads: int
    edited: bool

    def payload(self) -> dict[str, Any]:
        return {"reads": self.reads, "edited": self.edited}


def _unwrap(command: str) -> str:
    """The command inside ``bash -lc '...'``, as Codex runs it."""

    match = _SHELL_WRAP.match(command.strip())
    if not match:
        return command
    try:
        parts = shlex.split(match.group(1))
    except ValueError:
        return match.group(1)
    return parts[0] if len(parts) == 1 else match.group(1)


def _mask_quotes(command: str) -> tuple[str, str]:
    """The command with quoted text blanked out, and with unquoted newlines as ``;``.

    The first is for finding redirects, which a ``>`` inside quotes is not; the
    second is for splitting into commands. Both keep the command's length.
    """

    masked: list[str] = []
    split: list[str] = []
    quote = ""
    i = 0
    while i < len(command):
        ch = command[i]
        if quote:
            if ch == quote:
                quote = ""
                masked.append(ch)
            elif ch == "\\" and quote == '"' and i + 1 < len(command):
                masked.append("xx")
                split.append(ch + command[i + 1])
                i += 2
                continue
            else:
                masked.append("x" if ch != "\n" else "\n")
            split.append(ch)
        elif ch in "'\"":
            quote = ch
            masked.append(ch)
            split.append(ch)
        elif ch == "\\" and i + 1 < len(command):
            masked.append("xx")
            split.append(ch + command[i + 1])
            i += 2
            continue
        else:
            masked.append(ch)
            split.append(";" if ch == "\n" else ch)
        i += 1
    return "".join(masked), "".join(split)


def _strip_heredocs(command: str) -> tuple[str, bool]:
    """The command without heredoc bodies, and whether a Python body writes a file."""

    out: list[str] = []
    writes = False
    pending: list[tuple[str, bool]] = []
    body: list[str] = []
    for line in command.split("\n"):
        if pending:
            delimiter, python = pending[0]
            if line.strip() == delimiter:
                pending.pop(0)
                writes = writes or (python and bool(_PY_WRITE.search("\n".join(body))))
                body = []
            else:
                body.append(line)
            continue
        out.append(line)
        masked, _ = _mask_quotes(line)
        for match in _HEREDOC_START.finditer(line):
            if masked[match.start() : match.start() + 2] == "<<":
                python = bool(re.search(r"(?:^|[\s/;&|])python[\d.]*\b", line[: match.start()]))
                pending.append((match.group(1), python))
    return "\n".join(out), writes


_OPERATORS = re.compile(r"&&|\|\||;;|[;&|()]")


def _segments(command: str) -> list[list[str]]:
    """The simple commands of a command line, each as words.

    A line is split where the shell starts another command: at ``&&``, ``||``,
    ``;``, ``&``, ``|``, at a subshell's ``(`` and ``)``, and at a group's
    ``{`` and ``}`` (which only count when they stand as words, so ``{a,b}``
    is not one). So ``(a || b) | tail`` is ``a``, ``b`` and ``tail``.

    A ``$( )`` command substitution is split the same way: the shell runs what
    is inside it, so ``echo $(pytest x)`` is the commands ``echo`` and
    ``pytest x`` (the ``$`` is dropped). Quoted text is one word, so
    ``'(pytest x)'`` and ``echo "(pytest x)"`` run nothing; a substitution
    inside double quotes is likewise not looked into.
    """

    # An escaped parenthesis (``find \\( -name a \\)``) is a word's own character.
    command = command.replace("\\(", "\ue000").replace("\\)", "\ue001")
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:
        words = command.split()
    out: list[list[str]] = [[]]
    for index, word in enumerate(words):
        if word and set(word) <= set(";&|()"):
            for _ in _OPERATORS.findall(word):
                out.append([])
            continue
        if word in {"{", "}"}:
            out.append([])
            continue
        if word == "$" and words[index + 1 : index + 2] == ["("]:
            continue
        out[-1].append(word.replace("\ue000", "(").replace("\ue001", ")"))
    return [segment for segment in out if segment]


def _git_subcommand(words: list[str]) -> str:
    rest = words[1:]
    while rest and rest[0].startswith("-"):
        # git -C <dir> / -c <k=v> take a value; other global flags do not.
        rest = rest[2:] if rest[0] in {"-C", "-c"} and len(rest) > 1 else rest[1:]
    return rest[0] if rest else ""


def _segment_kind(words: list[str]) -> str | None:
    """``"change"``, ``"read"``, ``"neutral"`` or None for one simple command."""

    while words and re.fullmatch(r"\w+=\S*", words[0]):
        words = words[1:]
    if not words:
        return None
    name = words[0].rsplit("/", 1)[-1]
    if name in _NEUTRAL:
        return "neutral"
    if name == "apply_patch":
        return "change"
    if name == "tee" or name in _FILE_COMMANDS:
        return "change"
    if name.startswith("python") and any(_PY_WRITE.search(w) for w in words[1:]):
        return "change"
    if name == "sed":
        flags = [w for w in words[1:] if w.startswith("-") and not w.startswith("--")]
        if any(f.startswith("-i") or ("i" in f[1:] and "e" not in f and "n" not in f) for f in flags) or "--in-place" in words:
            return "change"
        return "read" if any("n" in f[1:] for f in flags) else None
    if name == "perl":
        return "change" if any(re.fullmatch(r"-\w*i\w*", w) for w in words[1:]) else None
    if name == "git":
        sub = _git_subcommand(words)
        if sub == "apply":
            return "read" if _GIT_APPLY_READ_ONLY & set(words) else "change"
        if sub in _GIT_CHANGES:
            return "change"
        return "read" if sub in _READ_GIT else None
    return "read" if name in _READ_COMMANDS else None


def classify_command(command: str) -> str | None:
    """Whether a shell command line reads, changes a file, or is neither.

    A line is a change when any part of it changes; it is a read only when
    every part of it reads (``cat a | grep b`` is a read, ``cat a > b`` is not).
    """

    command, python_writes = _strip_heredocs(_unwrap(command))
    if python_writes:
        return "change"
    masked, command = _mask_quotes(command)
    # Redirects that write no file: ``2>&1``, ``>/dev/null``.
    no_file = r"(?:\d|&)?>>?\s*(?:&\d|/dev/null\b)"
    masked = re.sub(no_file, " ", masked)
    command = re.sub(no_file, " ", command)
    if _REDIRECT.search(masked) or _HEREDOC_TO_FILE.search(masked):
        return "change"
    kinds = [_segment_kind(words) for words in _segments(command)]
    if "change" in kinds:
        return "change"
    kinds = [kind for kind in kinds if kind != "neutral"]
    return "read" if kinds and all(kind == "read" for kind in kinds) else None


def _classify_event(event_type: str, payload: Mapping[str, Any]) -> str | None:
    if event_type == "agent.command":
        return classify_command(str(payload.get("command") or ""))
    tool = str(payload.get("tool") or "")
    if event_type in {"agent.file_change", "agent.tool_use"}:
        if tool in READ_TOOLS:
            return "read"
        if tool in CHANGE_TOOLS:
            return "change"
        # Codex's ``commandExecution`` tool use repeats an ``agent.command``; it is not counted again.
        if tool == "commandExecution":
            return None
        if event_type == "agent.file_change":
            return "change"
    return None


def reads_before_first_change(events: Iterable[tuple[str, Mapping[str, Any]]]) -> StepReads:
    """Count a run's reading tool calls before its first change.

    *events* are the run's stored events in order, as ``(event_type, payload)``;
    those that are not tool calls are ignored. A run that changed nothing
    reports every read it made, with ``edited`` False.
    """

    reads = 0
    for event_type, payload in events:
        kind = _classify_event(event_type, payload)
        if kind == "change":
            return StepReads(reads, True)
        if kind == "read":
            reads += 1
    return StepReads(reads, False)
