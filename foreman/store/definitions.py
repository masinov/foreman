"""A project's own roles and workflows, as TOML text with every revision (ADR-0024)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .base import StoreBase

DEFINITION_KINDS: tuple[str, ...] = ("role", "workflow")


@dataclass(frozen=True, slots=True)
class StoredDefinition:
    """One revision of one role or workflow a project keeps for itself."""

    project_id: str
    kind: str
    definition_id: str
    revision: int
    body: str
    removed: bool
    changed_by: str
    changed_at: str


def _row(row: sqlite3.Row) -> StoredDefinition:
    return StoredDefinition(
        project_id=row["project_id"],
        kind=row["kind"],
        definition_id=row["definition_id"],
        revision=int(row["revision"]),
        body=row["body"],
        removed=bool(row["removed"]),
        changed_by=row["changed_by"],
        changed_at=row["changed_at"],
    )


_COLUMNS = "project_id, kind, definition_id, revision, body, removed, changed_by, changed_at"


class DefinitionStore(StoreBase):
    """Revisions of a project's own definitions; the highest revision is current."""

    def add_definition_revision(
        self,
        *,
        project_id: str,
        kind: str,
        definition_id: str,
        body: str,
        removed: bool,
        changed_by: str,
        changed_at: str,
    ) -> StoredDefinition:
        """Append a revision and return it."""

        result: list[int] = []

        def _write(connection: sqlite3.Connection) -> None:
            revision = int(
                connection.execute(
                    "SELECT COALESCE(MAX(revision), 0) + 1 FROM definitions "
                    "WHERE project_id = ? AND kind = ? AND definition_id = ?",
                    (project_id, kind, definition_id),
                ).fetchone()[0]
            )
            connection.execute(
                f"INSERT INTO definitions ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (project_id, kind, definition_id, revision, body, int(removed), changed_by, changed_at),
            )
            result.append(revision)

        self._write(_write)
        return StoredDefinition(
            project_id, kind, definition_id, result[0], body, removed, changed_by, changed_at
        )

    def current_definitions(self, project_id: str, kind: str | None = None) -> list[StoredDefinition]:
        """The current revision of each definition the project keeps, removed ones left out."""

        where = "d.project_id = ?"
        params: list[str] = [project_id]
        if kind is not None:
            where += " AND d.kind = ?"
            params.append(kind)
        rows = self._connection.execute(
            f"SELECT {_COLUMNS} FROM definitions d WHERE {where} AND d.revision = ("
            "SELECT MAX(revision) FROM definitions m WHERE m.project_id = d.project_id "
            "AND m.kind = d.kind AND m.definition_id = d.definition_id) "
            "AND d.removed = 0 ORDER BY d.kind, d.definition_id",
            tuple(params),
        ).fetchall()
        return [_row(row) for row in rows]

    def definition_revisions(self, project_id: str, kind: str, definition_id: str) -> list[StoredDefinition]:
        """Every revision of one definition, newest first."""

        rows = self._connection.execute(
            f"SELECT {_COLUMNS} FROM definitions WHERE project_id = ? AND kind = ? "
            "AND definition_id = ? ORDER BY revision DESC",
            (project_id, kind, definition_id),
        ).fetchall()
        return [_row(row) for row in rows]
