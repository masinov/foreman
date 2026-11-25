"""The record a role's step produces (ADR-0041 section 2, ADR-0042).

A role declares a record in its TOML: a kind and named fields, each marked
required or not. This module owns the declaration (loading and refusing a
malformed one), what the agent is told to return, and checking a returned
record against the declaration. It knows nothing about runs or storage.

```toml
[completion.record]
kind = "developer_report"

[[completion.record.fields]]
name = "summary"
type = "text"
required = true
description = "What changed and why."
```

Field types:
- ``text``: a string; required means not blank.
- ``bool``: true or false.
- ``text_list``: a list of strings; required means the key is present, and an
  empty list says there is nothing to list.
- ``records``: a list of objects, each described by the field's own
  ``fields`` (one level; the entries cannot nest further).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..domain.errors import ForemanError

#: The info string of the fenced block an agent returns its record in.
RECORD_FENCE = "foreman-record"

FIELD_TYPES: tuple[str, ...] = ("text", "bool", "text_list", "records")

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_FENCED_RECORD = re.compile(
    rf"^[ \t]*```[ \t]*{re.escape(RECORD_FENCE)}[ \t]*\n(.*?)^[ \t]*```[ \t]*$",
    re.DOTALL | re.MULTILINE,
)

#: What a detail starts with when the record broke the declaration.
RECORD_PROBLEM_PREFIX = "The step's record is not usable"


class RecordDeclarationError(ForemanError):
    """Raised when a role's record declaration is malformed."""


@dataclass(frozen=True, slots=True)
class RecordField:
    """One named field of a record."""

    name: str
    type: str
    required: bool
    description: str = ""
    #: For ``records``: the fields of each entry.
    fields: tuple["RecordField", ...] = ()


@dataclass(frozen=True, slots=True)
class RecordDeclaration:
    """The record a role's step produces."""

    kind: str
    fields: tuple[RecordField, ...] = field(default=())

    def instructions(self, marker: str = "") -> str:
        """What the agent is told about returning the record."""

        lines = [
            f"Return the {self.kind.replace('_', ' ')} as one JSON object in a fenced block whose",
            f"info string is `{RECORD_FENCE}`, in your final message"
            + (f", before the `{marker}` line." if marker else "."),
            "The block holds only JSON. Fields:",
        ]
        lines.extend(_field_lines(self.fields, indent=0))
        lines.append("")
        lines.append(f"```{RECORD_FENCE}")
        lines.append(json.dumps(_example(self.fields), indent=2))
        lines.append("```")
        lines.append(
            "A final message with no such block, or one that breaks the shape above, "
            "ends the step as an error."
        )
        return "\n".join(lines)


def parse_record_declaration(data: Any, source: Path | str) -> RecordDeclaration | None:
    """The declaration a role's ``[completion.record]`` table holds, or None when it has none."""

    if data is None:
        return None
    where = f"{source}: completion.record"
    if not isinstance(data, Mapping):
        raise RecordDeclarationError(f"{where} must be a table.")
    unknown = sorted(set(data) - {"kind", "fields"})
    if unknown:
        raise RecordDeclarationError(
            f"{where} has unknown key(s) {', '.join(unknown)}; it takes kind and fields."
        )
    kind = data.get("kind")
    if not isinstance(kind, str) or not _NAME.match(kind):
        raise RecordDeclarationError(
            f"{where}.kind must be a lowercase name such as developer_report; got {kind!r}."
        )
    fields = _parse_fields(data.get("fields"), where, nested=False)
    return RecordDeclaration(kind=kind, fields=fields)


def _parse_fields(raw: Any, where: str, *, nested: bool) -> tuple[RecordField, ...]:
    if not isinstance(raw, list) or not raw:
        raise RecordDeclarationError(f"{where} must declare at least one field.")
    fields: list[RecordField] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        label = f"{where}.fields #{index}"
        if not isinstance(item, Mapping):
            raise RecordDeclarationError(f"{label} must be a table.")
        name = item.get("name")
        if not isinstance(name, str) or not _NAME.match(name):
            raise RecordDeclarationError(f"{label}.name must be a lowercase name; got {name!r}.")
        label = f"{where}.fields {name!r}"
        if name in seen:
            raise RecordDeclarationError(f"{label} is declared twice.")
        seen.add(name)
        unknown = sorted(set(item) - {"name", "type", "required", "description", "fields"})
        if unknown:
            raise RecordDeclarationError(f"{label} has unknown key(s) {', '.join(unknown)}.")
        field_type = item.get("type")
        if field_type not in FIELD_TYPES:
            raise RecordDeclarationError(
                f"{label}.type must be one of {', '.join(FIELD_TYPES)}; got {field_type!r}."
            )
        required = item.get("required")
        if not isinstance(required, bool):
            raise RecordDeclarationError(
                f"{label}.required must be true or false: say whether the field is required."
            )
        description = item.get("description", "")
        if not isinstance(description, str):
            raise RecordDeclarationError(f"{label}.description must be a string.")
        inner: tuple[RecordField, ...] = ()
        if field_type == "records":
            if nested:
                raise RecordDeclarationError(f"{label}: a record's entries cannot hold records.")
            inner = _parse_fields(item.get("fields"), label, nested=True)
        elif "fields" in item:
            raise RecordDeclarationError(f"{label}: only a field of type records takes fields.")
        fields.append(
            RecordField(
                name=name,
                type=field_type,
                required=required,
                description=description.strip(),
                fields=inner,
            )
        )
    return tuple(fields)


# ── what the agent returns ───────────────────────────────────────────────


def split_record_block(text: str) -> tuple[str | None, str]:
    """The last record block of a message, and the message without any record block."""

    blocks = _FENCED_RECORD.findall(text)
    stripped = _FENCED_RECORD.sub("", text).strip()
    return (blocks[-1] if blocks else None), stripped


def read_record(
    declaration: RecordDeclaration, text: str
) -> tuple[dict[str, Any] | None, str | None]:
    """Parse and check the record in a final message: ``(fields, None)`` or ``(None, problem)``."""

    block, _ = split_record_block(text)
    if block is None:
        return None, (
            f"The final message has no ```{RECORD_FENCE}``` block holding the "
            f"{declaration.kind} record."
        )
    try:
        value = json.loads(block)
    except ValueError as exc:
        return None, f"The {declaration.kind} record is not valid JSON: {exc}."
    problems = check_record(declaration, value)
    if problems:
        return None, "; ".join(problems)
    return value, None


def check_record(declaration: RecordDeclaration, value: Any) -> list[str]:
    """Every way *value* breaks the declaration, in words; empty when it keeps it."""

    if not isinstance(value, dict):
        return [f"The {declaration.kind} record must be a JSON object."]
    return _check_fields(declaration.fields, value, "")


def _check_fields(fields: tuple[RecordField, ...], value: Mapping[str, Any], path: str) -> list[str]:
    problems: list[str] = []
    for spec in fields:
        where = f"{path}{spec.name}"
        if spec.name not in value or value[spec.name] is None:
            if spec.required:
                problems.append(f"`{where}` is required and missing")
            continue
        item = value[spec.name]
        if spec.type == "text":
            if not isinstance(item, str):
                problems.append(f"`{where}` must be text")
            elif spec.required and not item.strip():
                problems.append(f"`{where}` is required and blank")
        elif spec.type == "bool":
            if not isinstance(item, bool):
                problems.append(f"`{where}` must be true or false")
        elif spec.type == "text_list":
            if not isinstance(item, list) or any(not isinstance(entry, str) for entry in item):
                problems.append(f"`{where}` must be a list of text")
        elif spec.type == "records":
            if not isinstance(item, list) or any(not isinstance(entry, dict) for entry in item):
                problems.append(f"`{where}` must be a list of objects")
            else:
                for number, entry in enumerate(item, start=1):
                    problems.extend(_check_fields(spec.fields, entry, f"{where}[{number}]."))
    unknown = sorted(set(value) - {spec.name for spec in fields})
    if unknown:
        label = path.rstrip(".") or "the record"
        problems.append(f"{label} has undeclared field(s) {', '.join(unknown)}")
    return problems


# ── what the agent is shown ──────────────────────────────────────────────


def _field_lines(fields: tuple[RecordField, ...], *, indent: int) -> list[str]:
    pad = "  " * indent
    lines: list[str] = []
    for spec in fields:
        kind = {
            "text": "text",
            "bool": "true or false",
            "text_list": "list of text, empty when there is none",
            "records": "list of objects",
        }[spec.type]
        need = "required" if spec.required else "optional"
        said = f": {spec.description}" if spec.description else ""
        lines.append(f"{pad}- `{spec.name}` ({kind}, {need}){said}")
        if spec.fields:
            lines.extend(_field_lines(spec.fields, indent=indent + 1))
    return lines


def _example(fields: tuple[RecordField, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for spec in fields:
        if spec.type == "text":
            out[spec.name] = "..."
        elif spec.type == "bool":
            out[spec.name] = True
        elif spec.type == "text_list":
            out[spec.name] = ["..."]
        else:
            out[spec.name] = [_example(spec.fields)]
    return out
