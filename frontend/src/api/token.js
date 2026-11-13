// The dashboard token lives where the pre-v7 application keeps it, so a
// person signed in on one is signed in on the other.
const TOKEN_STORAGE_KEY = "foreman.dashboard.token";

function defaultStorage() {
  try {
    return globalThis.localStorage || null;
  } catch {
    return null;
  }
}

export function readDashboardToken(storage = defaultStorage()) {
  try {
    return storage?.getItem(TOKEN_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

/** Forget the stored dashboard token, so this browser stops presenting it. */
export function clearDashboardToken(storage = defaultStorage()) {
  try {
    storage?.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // Storage that cannot be written cannot hold a token either.
  }
}

/** Keep the dashboard token in this browser, so every request presents it. */
export function writeDashboardToken(token, storage = defaultStorage()) {
  try {
    storage?.setItem(TOKEN_STORAGE_KEY, token);
    return true;
  } catch {
    return false;
  }
}
