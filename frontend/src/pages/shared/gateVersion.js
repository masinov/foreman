import { shortSha } from "../../ui/format";

// The version a person decides on at a gate (`gate_version` from the API):
// the branch's head for a merge, the plan's fingerprint for a plan. An
// approval names the version the page showed; the server refuses one that
// is no longer current.

export const MERGE_APPROVAL = "merge_approval";
export const PLAN_APPROVAL = "plan_approval";

/** The one value an approval names for a version, or null. */
export function versionToken(version) {
  if (!version) return null;
  return version.token ?? (version.kind === MERGE_APPROVAL ? version.branch_sha : version.fingerprint) ?? null;
}

/**
 * The commit a row shows at a merge gate, and so the one its Approve names:
 * the commit its checks ran on, else the branch's head. If the branch moved
 * after the checks, the server refuses the approval and says so.
 */
export function shownCommit(checkedCommit, version) {
  return checkedCommit || version?.branch_sha || null;
}

/** "abc1234" for a merge, "plan abc1234" for a plan: the version in the words of a line. */
export function versionWords(version) {
  const short = shortSha(versionToken(version));
  if (!short) return "";
  return version.kind === PLAN_APPROVAL || (!version.branch_sha && version.fingerprint) ? `plan ${short}` : short;
}

/**
 * The words that say which version an approval was recorded against:
 * "at abc1234" when the request named it, "(recorded at abc1234)" when it
 * did not; a plan's is "plan abc1234". Empty when the gate has no version.
 */
export function recordedWords(version, named) {
  const what = versionWords(version);
  if (!what) return "";
  return named ? `at ${what}` : `(recorded at ${what})`;
}
