"""API tokens other systems use to file work."""

from __future__ import annotations

import sqlite3
from typing import Sequence
from uuid import uuid4

from ..api_tokens import ApiTokenError, hash_token_secret, mint_token_secret, normalize_scopes
from ..models import (
    ApiToken,
    utc_now_text,
)

from .base import (
    StoreBase,
)
from .rows import (
    _json_dumps,
    _row_to_api_token,
)


class ApiTokenStore(StoreBase):
    """API tokens other systems use to file work."""

    def create_api_token(
        self,
        *,
        project_id: str,
        name: str,
        scopes: Sequence[str] | None = None,
        created_by: str = "human",
        token_id: str | None = None,
    ) -> tuple[ApiToken, str]:
        """Mint one project API token.

        Returns the persisted record and the secret, in that order. The secret
        is the caller's only copy: it is not stored, cannot be recovered, and
        must be handed to a person or a config store immediately.
        """

        cleaned_name = (name or "").strip()
        if not cleaned_name:
            raise ValueError("An API token needs a name.")
        secret = mint_token_secret()
        token = ApiToken(
            id=token_id or f"tok-{uuid4().hex[:12]}",
            project_id=project_id,
            name=cleaned_name,
            token_hash=hash_token_secret(secret),
            scopes=list(normalize_scopes(scopes)),
            created_by=created_by,
        )

        def _write(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                INSERT INTO api_tokens (
                    id, project_id, name, token_hash, scopes_json, created_by,
                    created_at, last_used_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token.id,
                    token.project_id,
                    token.name,
                    token.token_hash,
                    _json_dumps(token.scopes),
                    token.created_by,
                    token.created_at,
                    token.last_used_at,
                    token.revoked_at,
                ),
            )

        self._write(_write)
        return token, secret

    def find_api_token(self, secret: str) -> ApiToken | None:
        """Return the live token a secret authenticates, bumping its last use.

        Lookup is by hash against the unique index, so a wrong secret costs one
        indexed miss and never a scan. Revoked tokens are invisible here --
        authentication has exactly one way to succeed.
        """

        try:
            token_hash = hash_token_secret(secret)
        except ApiTokenError:
            return None
        row = self._connection.execute(
            "SELECT * FROM api_tokens WHERE token_hash = ? AND revoked_at IS NULL",
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        token = _row_to_api_token(row)
        used_at = utc_now_text()

        def _touch(connection: sqlite3.Connection) -> None:
            connection.execute(
                "UPDATE api_tokens SET last_used_at = ? WHERE id = ?",
                (used_at, token.id),
            )

        self._write(_touch)
        token.last_used_at = used_at
        return token

    def get_api_token(self, token_id: str) -> ApiToken | None:
        """Return one API token by identifier, revoked or not."""

        row = self._connection.execute(
            "SELECT * FROM api_tokens WHERE id = ?",
            (token_id,),
        ).fetchone()
        return _row_to_api_token(row) if row else None

    def list_api_tokens(
        self, project_id: str, *, include_revoked: bool = True
    ) -> list[ApiToken]:
        """List a project's API tokens, most recently created first."""

        query = "SELECT * FROM api_tokens WHERE project_id = ?"
        if not include_revoked:
            query += " AND revoked_at IS NULL"
        query += " ORDER BY created_at DESC, id DESC"
        rows = self._connection.execute(query, (project_id,)).fetchall()
        return [_row_to_api_token(row) for row in rows]

    def revoke_api_token(self, token_id: str) -> ApiToken | None:
        """Revoke one token. Returns None when no such token exists.

        Revocation is a timestamp, not a delete: the audit trail keeps the row
        so `created_by = "api:<name>"` on old tasks still resolves to something.
        Revoking an already-revoked token keeps the original timestamp.
        """

        existing = self.get_api_token(token_id)
        if existing is None:
            return None
        if existing.revoked_at is not None:
            return existing
        revoked_at = utc_now_text()

        def _write(connection: sqlite3.Connection) -> None:
            connection.execute(
                "UPDATE api_tokens SET revoked_at = ? WHERE id = ?",
                (revoked_at, token_id),
            )

        self._write(_write)
        existing.revoked_at = revoked_at
        return existing
