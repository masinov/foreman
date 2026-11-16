"""Roles and workflows kept as TOML text, with every revision (ADR-0024).

A project keeps its own in ``definitions``; the workspace keeps the defaults
it changed in ``workspace_definitions``. Every method takes the project id,
or ``None`` for the workspace.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .base import StoreBase

DEFINITION_KINDS: tuple[str, ...] = ("role", "workflow")


@dataclass(frozen=True, slots=True)
class StoredDefinition:
    """One revision of one role or workflow; ``project_id`` is ``None`` for the workspace."""

    project_id: str | None
    kind: str
    definition_id: str
    revision: int
    body: str
    removed: bool
    changed_by: str
    changed_at: str


_COLUMNS = "kind, definition_id, revision, body, removed, changed_by, changed_at"


def _row(project_id: str | None, row: sqlite3.Row) -> StoredDefinition:
    return StoredDefinition(
        project_id=project_id,
        kind=row["kind"],
        definition_id=row["definition_id"],
        revision=int(row["revision"]),
        body=row["body"],
        removed=bool(row["removed"]),
        changed_by=row["changed_by"],
        changed_at=row["changed_at"],
    )


def _scope(project_id: str | None) -> tuple[str, str, tuple[str, ...]]:
    """The table, the WHERE clause that selects the scope, and its parameters."""

    if project_id is None:
        return "workspace_definitions", "1 = 1", ()
    return "definitions", "project_id = ?", (project_id,)


class DefinitionStore(StoreBase):
    """Revisions of definitions; the highest revision of each is current."""

    def add_definition_revision(
        self,
        *,
        project_id: str | None,
        kind: str,
        definition_id: str,
        body: str,
        removed: bool,
        changed_by: str,
        changed_at: str,
    ) -> StoredDefinition:
        """Append a revision and return it."""

        table, where, scope = _scope(project_id)
        result: list[int] = []

        def _write(connection: sqlite3.Connection) -> None:
            revision = int(
                connection.execute(
                    f"SELECT COALESCE(MAX(revision), 0) + 1 FROM {table} "
                    f"WHERE {where} AND kind = ? AND definition_id = ?",
                    (*scope, kind, definition_id),
                ).fetchone()[0]
            )
            values = (kind, definition_id, revision, body, int(removed), changed_by, changed_at)
            if project_id is None:
                connection.execute(
                    f"INSERT INTO {table} ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)", values
                )
            else:
                connection.execute(
                    f"INSERT INTO {table} (project_id, {_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (project_id, *values),
                )
            result.append(revision)

        self._write(_write)
        return StoredDefinition(
            project_id, kind, definition_id, result[0], body, removed, changed_by, changed_at
        )

    def current_definitions(
        self, project_id: str | None, kind: str | None = None
    ) -> list[StoredDefinition]:
        """The current revision of each definition kept in the scope, removed ones left out."""

        table, where, scope = _scope(project_id)
        params: list[str] = list(scope)
        kind_clause = ""
        if kind is not None:
            kind_clause = " AND d.kind = ?"
            params.append(kind)
        same_scope = "" if project_id is None else "m.project_id = d.project_id AND "
        rows = self._connection.execute(
            f"SELECT {_COLUMNS} FROM {table} d WHERE {where}{kind_clause} AND d.revision = ("
            f"SELECT MAX(revision) FROM {table} m WHERE {same_scope}"
            "m.kind = d.kind AND m.definition_id = d.definition_id) "
            "AND d.removed = 0 ORDER BY d.kind, d.definition_id",
            tuple(params),
        ).fetchall()
        return [_row(project_id, row) for row in rows]

    def definition_revisions(
        self, project_id: str | None, kind: str, definition_id: str
    ) -> list[StoredDefinition]:
        """Every revision of one definition, newest first."""

        table, where, scope = _scope(project_id)
        rows = self._connection.execute(
            f"SELECT {_COLUMNS} FROM {table} WHERE {where} AND kind = ? "
            "AND definition_id = ? ORDER BY revision DESC",
            (*scope, kind, definition_id),
        ).fetchall()
        return [_row(project_id, row) for row in rows]
