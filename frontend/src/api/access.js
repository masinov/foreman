import { segment } from "./client";

/**
 * Who is acting, what can reach Foreman and where it speaks: the reads and
 * writes behind workspace settings. Each write is the operation the CLI has
 * (`foreman token`, `foreman notify`) on the same service.
 */

/**
 * Who the server says is acting: `{ authentication: "none" | "token", name,
 * can_sign_out, identity_provider }`.
 */
export function getSession(client, options) {
  return client.get("/session", options);
}

/** `{ database_path, version, address }` of the machine the server runs on. */
export function getMachine(client, options) {
  return client.get("/machine", options);
}

/** The agent backends found on this machine and the models roles ask them for. */
export function listRunners(client, options) {
  return client.get("/runners", options).then((payload) => payload?.runners ?? []);
}

/** Every role definition, with the file it is read from. */
export function listRoles(client, options) {
  return client.get("/roles", options).then((payload) => payload?.roles ?? []);
}

/** API tokens across projects, newest first, and the scopes a token may carry. */
export function listTokens(client, options) {
  return client
    .get("/tokens", options)
    .then((payload) => ({ tokens: payload?.tokens ?? [], scopes: payload?.scopes ?? [] }));
}

/** Create a token. The answer carries `secret`, which the server never shows again. */
export function createToken(client, projectId, { name, scopes }, options) {
  return client.post(`/projects/${segment(projectId)}/tokens`, { name, scopes }, options);
}

export function revokeToken(client, tokenId, options) {
  return client.post(`/tokens/${segment(tokenId)}/revoke`, undefined, options);
}

/** Notification channels across projects, and the kinds a channel may be. */
export function listChannels(client, options) {
  return client
    .get("/notification-channels", options)
    .then((payload) => ({ channels: payload?.channels ?? [], kinds: payload?.kinds ?? [] }));
}

export function createChannel(client, projectId, { name, url, kind, secretEnv }, options) {
  const body = { name, url };
  if (kind) body.kind = kind;
  if (secretEnv) body.secret_env = secretEnv;
  return client.post(`/projects/${segment(projectId)}/notification-channels`, body, options);
}

export function deleteChannel(client, channelId, options) {
  return client.delete(`/notification-channels/${segment(channelId)}`, options);
}
