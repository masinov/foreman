import { useEffect, useRef } from "react";

import { useApiClient } from "./ApiProvider";

/**
 * Follow an event stream (`/sprints/{id}/stream`, `/projects/{id}/stream`)
 * while `path` is set. `onEvent(event)` runs for every engine event the
 * stream carries; the latest `onEvent` is always the one called, so callers
 * need not memoise it. The stream closes when `path` changes or the component
 * goes away.
 */
export function useEventStream(path, onEvent) {
  const client = useApiClient();
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!path) return undefined;
    return client.stream(path, {
      onMessage: (data) => {
        if (data?.type === "event" && data.event) onEventRef.current(data.event);
      },
    });
  }, [client, path]);
}
