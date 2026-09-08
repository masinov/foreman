"""Secret handling for the project API tokens that authenticate intake.

The one rule this module exists to enforce: Foreman never keeps the secret.
:func:`mint_token_secret` produces it, the caller shows it to a person once,
and only :func:`hash_token_secret` output reaches SQLite or a log line. Keeping
minting, hashing, and the scope vocabulary here means the store, the CLI, and
the HTTP layer all agree on what a token is without any of them re-deriving the
format.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Iterable

#: Every minted secret starts with this. It is not a security measure -- it
#: lets the dashboard's token middleware recognise "this is a project API
#: token, not the shared dashboard token" without a database round trip, and it
#: makes a leaked secret greppable in the systems that store it.
TOKEN_PREFIX = "fmn_"

#: Bytes of entropy behind each secret, before URL-safe encoding.
_SECRET_BYTES = 32

#: The scope that authorizes ``POST /api/projects/{id}/intake``.
INTAKE_SCOPE = "intake"

#: Every scope a token may carry today. New scopes are added here and become
#: valid immediately; `scopes_json` already stores a list.
API_TOKEN_SCOPES: frozenset[str] = frozenset({INTAKE_SCOPE})


class ApiTokenError(ValueError):
    """Raised when a token secret or scope set is malformed."""


def mint_token_secret() -> str:
    """Return one new token secret. The only place secrets are created."""

    return f"{TOKEN_PREFIX}{secrets.token_urlsafe(_SECRET_BYTES)}"


def hash_token_secret(secret: str) -> str:
    """Return the SHA-256 hex digest persisted in place of ``secret``.

    Secrets are high-entropy random strings, not passwords, so a single SHA-256
    pass is the right primitive: there is nothing for a slow KDF to protect
    against when the search space is 256 bits.
    """

    cleaned = (secret or "").strip()
    if not cleaned:
        raise ApiTokenError("An API token secret cannot be empty.")
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


def secrets_match(presented: str, expected_hash: str) -> bool:
    """Compare a presented secret against a stored hash in constant time."""

    try:
        candidate = hash_token_secret(presented)
    except ApiTokenError:
        return False
    return hmac.compare_digest(candidate, expected_hash)


def looks_like_api_token(presented: str | None) -> bool:
    """Return True when a presented credential has the API-token shape.

    Used by the dashboard middleware to reject a project API token on the
    routes it is not meant for, without hitting the database for every request.
    """

    return bool(presented) and presented.strip().startswith(TOKEN_PREFIX)


def normalize_scopes(scopes: Iterable[str] | None) -> tuple[str, ...]:
    """Validate and de-duplicate a scope set, preserving caller order.

    An empty request defaults to ``intake``: a token with no scope can do
    nothing, which is never what the caller meant.
    """

    cleaned: list[str] = []
    for scope in scopes or ():
        value = str(scope).strip().lower()
        if not value:
            continue
        if value not in API_TOKEN_SCOPES:
            raise ApiTokenError(
                f"Unknown API token scope: {value}. "
                f"Expected one of: {', '.join(sorted(API_TOKEN_SCOPES))}."
            )
        if value not in cleaned:
            cleaned.append(value)
    return tuple(cleaned) or (INTAKE_SCOPE,)
