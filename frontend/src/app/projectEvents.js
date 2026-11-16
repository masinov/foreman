// Every event on the stream of the project being looked at. The app follows
// that stream once (useLiveData); a part of a page that needs the events
// themselves, such as the output of a running step, listens here instead of
// opening a stream of its own.

const listeners = new Set();

/** Hand one event from the project's stream to whoever listens. */
export function publishProjectEvent(event) {
  for (const listener of [...listeners]) listener(event);
}

/** Run `listener(event)` for every event. Returns how to stop. */
export function onProjectEvent(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
