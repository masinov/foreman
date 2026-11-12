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
