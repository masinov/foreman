"""What a service raises.

Each surface translates them: the API to an HTTP status and the error
envelope (ADR-0019), the CLI to a message and an exit code. Nothing below
the services knows about either.
"""

from __future__ import annotations


class ServiceError(Exception):
    """A request a service could not carry out. The message says why."""


class NotFoundError(ServiceError):
    """The record asked for does not exist (HTTP 404)."""


class InvalidRequestError(ServiceError):
    """What was sent is not valid (HTTP 400).

    ``field`` names the setting or field the message is about, when one is
    known, so a client can show the message beside it.
    """

    def __init__(self, message: str = "", *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class ActionFailedError(ServiceError):
    """The action could not be carried out (HTTP 500)."""


class VersionChangedError(ServiceError):
    """An approval names a version that is no longer current (HTTP 409).

    ``current`` is the version now, so the client shows it.
    """

    def __init__(self, message: str, current: dict[str, str | None]) -> None:
        super().__init__(message)
        self.current = current


class UnauthenticatedError(ServiceError):
    """The request presents no usable credential (HTTP 401)."""


class ForbiddenError(ServiceError):
    """A valid credential is not allowed to do this (HTTP 403)."""
