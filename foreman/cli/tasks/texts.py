"""Where ``foreman task edit`` gets a text: the command line, a file or the pipe, or an editor.

A person gives a description or acceptance criteria one of three ways. The
editor opens only when asked for (``--edit``) and only on a terminal; a script
or the manager would otherwise hang waiting for it.
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


class TextInputError(Exception):
    """A text option that cannot be honoured; the message says what to do."""


@dataclass(frozen=True)
class TextField:
    """A task text that can be edited, and how its options are named."""

    name: str  # the --edit value: "description" or "criteria"
    label: str  # how output names it
    mutation_field: str
    option: str
    file_option: str
    text_attr: str
    file_attr: str


TEXT_FIELDS: tuple[TextField, ...] = (
    TextField(
        "description", "Description", "description",
        "--description", "--description-file", "description", "description_file",
    ),
    TextField(
        "criteria", "Acceptance criteria", "acceptance_criteria",
        "--criteria", "--criteria-file", "criteria", "criteria_file",
    ),
)


def text_field(name: str) -> TextField:
    return next(field for field in TEXT_FIELDS if field.name == name)


def is_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def check_text_options(args: argparse.Namespace) -> None:
    """Refuse options that contradict each other, before anything is read."""

    stdin_users = []
    for field in TEXT_FIELDS:
        text = getattr(args, field.text_attr)
        path = getattr(args, field.file_attr)
        if text is not None and path is not None:
            raise TextInputError(f"Give {field.option} or {field.file_option}, not both.")
        if args.edit == field.name and (text is not None or path is not None):
            raise TextInputError(
                f"Give --edit {field.name} or {field.option}/{field.file_option}, not both."
            )
        if path == "-":
            stdin_users.append(field.file_option)
    if len(stdin_users) > 1:
        raise TextInputError("Standard input can be read once; only one text can come from `-`.")
    if args.edit is not None and not is_terminal():
        field = text_field(args.edit)
        raise TextInputError(
            "--edit opens an editor, which needs a terminal. "
            f"Use `{field.file_option} -` to give the text on standard input, "
            f"or `{field.file_option} PATH`."
        )


def read_text_option(field: TextField, args: argparse.Namespace) -> str | None:
    """The text given on the command line or in a file for ``field``; None if neither."""

    text = getattr(args, field.text_attr)
    if text is not None:
        return text
    path = getattr(args, field.file_attr)
    if path is None:
        return None
    try:
        if path == "-":
            return sys.stdin.read()
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise TextInputError(f"Could not read {path}: {exc}") from exc


def editor_command() -> list[str]:
    """``$VISUAL``, else ``$EDITOR``, else ``nano``, else ``vi``."""

    for name in ("VISUAL", "EDITOR"):
        value = os.environ.get(name, "").strip()
        if value:
            return shlex.split(value)
    for fallback in ("nano", "vi"):
        if shutil.which(fallback):
            return [fallback]
    raise TextInputError("No editor found. Set $VISUAL or $EDITOR, or use --description-file.")


def edit_in_editor(field: TextField, current: str | None) -> str:
    """Open ``current`` in the user's editor; return what it holds when it closes."""

    command = editor_command()
    handle, name = tempfile.mkstemp(prefix=f"foreman-{field.name}-", suffix=".md")
    path = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(current or "")
        try:
            completed = subprocess.run([*command, name], check=False)
        except OSError as exc:
            raise TextInputError(f"Could not start the editor {command[0]!r}: {exc}") from exc
        if completed.returncode != 0:
            raise TextInputError(
                f"The editor {command[0]!r} exited with status {completed.returncode}; "
                f"{field.label.lower()} not changed."
            )
        return path.read_text(encoding="utf-8")
    finally:
        path.unlink(missing_ok=True)
