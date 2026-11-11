"""Server-sent event streams over the store.

A stream holds one store connection and watches ``PRAGMA data_version``, so
it runs its query only when another process (the engine, usually) has
committed. Each message carries the event id, which a reconnecting client
sends back as ``Last-Event-ID`` to continue where it stopped.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
import time
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse

from ..dashboard_service import (
    STREAM_HEARTBEAT_SECONDS,
    STREAM_POLL_INTERVAL_SECONDS,
    DashboardService,
)
from .context import ApiContext, encode_sse_message, open_store

#: Given the service and the last event id the client has, return the next
#: messages, each ``{"event_id": ..., "payload": ...}``.
MessageSource = Callable[[DashboardService, str | None], list[dict[str, Any]]]


def event_stream_response(
    ctx: ApiContext,
    request: Request,
    *,
    after: str | None,
    next_messages: MessageSource,
) -> StreamingResponse:
    """Return an SSE response that follows ``next_messages`` until the client leaves."""

    async def event_stream() -> AsyncIterator[bytes]:
        last_event_id = request.headers.get("Last-Event-ID") or after
        last_heartbeat_at = time.monotonic()
        yield b"retry: 1000\n\n"

        with open_store(ctx.db_path) as store:
            api = DashboardService(store)
            last_data_version: int | None = None
            while True:
                if await request.is_disconnected():
                    break

                data_version = store.data_version()
                if data_version == last_data_version:
                    if time.monotonic() - last_heartbeat_at >= STREAM_HEARTBEAT_SECONDS:
                        yield b": keepalive\n\n"
                        last_heartbeat_at = time.monotonic()
                    await asyncio.sleep(STREAM_POLL_INTERVAL_SECONDS)
                    continue
                last_data_version = data_version

                messages = next_messages(api, last_event_id)
                if messages:
                    for message in messages:
                        last_event_id = str(message["event_id"])
                        yield encode_sse_message(message["payload"], event_id=last_event_id)
                    last_heartbeat_at = time.monotonic()
                elif time.monotonic() - last_heartbeat_at >= STREAM_HEARTBEAT_SECONDS:
                    yield b": keepalive\n\n"
                    last_heartbeat_at = time.monotonic()

                await asyncio.sleep(STREAM_POLL_INTERVAL_SECONDS)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
