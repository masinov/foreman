"""Browser-origin defences for the dashboard API.

A dashboard bound to loopback with no token is still reachable from the
operator's browser, and therefore from any web page that browser loads. Two
attacks follow: a cross-site request (a page on another origin posts to
``http://localhost:<port>/api/...``) and DNS rebinding (a hostile name is
re-pointed at 127.0.0.1 so the page becomes same-origin with the dashboard).

This module holds the decisions that stop both, as pure functions the HTTP
layer applies to every ``/api`` request:

* the ``Host`` header must name a trusted host when a trust list is set
  (the runtime sets one whenever no token protects the API), which defeats
  rebinding because the browser sends the hostile name;
* a request that carries an ``Origin`` must come from the dashboard's own
  origin or an allowlisted one, and a state-changing request the browser
  labels cross-site is refused, which defeats cross-site requests;
* a request body must be declared as JSON, which keeps state-changing
  requests out of the set a browser sends cross-origin without a preflight.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from urllib.parse import urlsplit

LOOPBACK_HOSTNAMES: tuple[str, ...] = ("localhost", "127.0.0.1", "::1")
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
JSON_MEDIA_TYPE = "application/json"


def hostname_of(host_header: str) -> str:
    """Return the lowercase hostname of a ``Host`` header, without the port."""

    value = host_header.strip().lower()
    if value.startswith("["):
        return value[1:].split("]", 1)[0]
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


def origin_netloc(origin: str) -> str | None:
    """Return the ``host[:port]`` of an ``Origin`` header, or ``None``.

    ``None`` covers the opaque origin browsers send as the literal ``null``
    (sandboxed frames, ``file:`` pages) and anything that is not an http(s)
    origin.
    """

    parts = urlsplit(origin.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    return parts.netloc.lower()


def trusted_hosts_for_bind(host: str) -> tuple[str, ...]:
    """Return the hostnames a token-less dashboard bound to ``host`` answers to."""

    names = list(LOOPBACK_HOSTNAMES)
    bound = hostname_of(host)
    if bound and bound not in names and bound not in {"0.0.0.0", "::"}:
        names.append(bound)
    return tuple(names)


def is_json_content_type(content_type: str | None) -> bool:
    """Return whether a ``Content-Type`` header declares a JSON body."""

    if not content_type:
        return False
    return content_type.split(";", 1)[0].strip().lower() == JSON_MEDIA_TYPE


def browser_request_violation(
    *,
    method: str,
    headers: Mapping[str, str],
    trusted_hosts: Iterable[str] | None,
    allowed_origins: Iterable[str] = (),
) -> str | None:
    """Return why a request must be refused, or ``None`` when it may proceed.

    ``headers`` is read case-insensitively by the caller's mapping (Starlette
    headers are). ``trusted_hosts`` of ``None`` disables the ``Host`` check;
    the runtime passes a list whenever the API has no token.
    """

    host_header = headers.get("host", "")
    if trusted_hosts is not None:
        trusted = {name.lower() for name in trusted_hosts}
        if hostname_of(host_header) not in trusted:
            return (
                "Forbidden: this dashboard does not answer to the requested host name. "
                "Open it through the address it was started on."
            )

    allowed = {
        netloc
        for netloc in (origin_netloc(origin) for origin in allowed_origins)
        if netloc is not None
    }
    origin = headers.get("origin")
    if origin is not None:
        netloc = origin_netloc(origin)
        same_origin = netloc is not None and netloc == host_header.strip().lower()
        if not same_origin and netloc not in allowed:
            return "Forbidden: cross-origin requests to the dashboard API are not allowed."
    elif method.upper() not in SAFE_METHODS and headers.get("sec-fetch-site", "").lower() == "cross-site":
        return "Forbidden: cross-site requests to the dashboard API are not allowed."
    return None
