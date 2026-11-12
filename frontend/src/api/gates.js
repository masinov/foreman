import { segment } from "./client";

/** How a person settles a proposed sprint order. */
export const GATE_RESOLUTIONS = { accept: "accepted", reject: "rejected" };

/** Accept (re-orders the sprints) or reject a proposed sprint order. */
export function resolveGate(client, gateId, resolution, options) {
  return client.patch(`/gates/${segment(gateId)}`, { resolution }, options);
}
