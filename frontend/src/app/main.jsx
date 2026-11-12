import { isLegacyPath } from "./paths";

// The entry decides which application owns this page. Both are loaded on
// demand, so neither's stylesheet reaches the other: the pre-v7 application
// under /dashboard/legacy (ADR-0020, decision 11), the rebuilt one elsewhere.
const container = document.getElementById("root");
const legacy = isLegacyPath(window.location.pathname);

if (legacy) {
  import("../legacy/mountLegacy").then(({ mountLegacy }) => mountLegacy(container, window));
} else {
  import("./mountApp").then(({ mountApp }) => mountApp(container, window));
}

// Back or forward across the boundary between the two applications loads the
// other one.
window.addEventListener("popstate", () => {
  if (isLegacyPath(window.location.pathname) !== legacy) {
    window.location.reload();
  }
});
