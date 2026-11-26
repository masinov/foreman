import { humanize } from "../../ui/format";
import { recordedWords } from "./gateVersion";

/** A task as a sentence names it: its key, else its title. */
export const taskName = (task) => task?.task_key || task?.task_title || task?.title || "the task";

/**
 * The one sentence an approval or a send-back is answered with, wherever it
 * is made (Needs you, the sprint's task list, the task's decision). `result`
 * is the API's answer (`next_step`, `engine_resident`, `held`); the step is named as
 * Activity names it. The server builds the same sentence for the CLI
 * (`decision_sentence` in `foreman/services/tasks.py`).
 *
 * "Approved FOR-51. Foreman goes on with Merge."
 * "Approved FOR-51 at abc1234. Foreman goes on with Merge." (the version it named)
 * "Approved FOR-51 (recorded at abc1234). Foreman goes on with Merge." (none named)
 * "Approved FOR-51. It goes on with Merge on Resume." (a task a user holds)
 * "Approved FOR-51. It waits at Merge until a worker runs."
 * "Sent FOR-51 back to Develop."
 */
export function decisionSentence(name, result, { sentBack = false } = {}) {
  const step = humanize(result?.next_step);
  if (sentBack) return step ? `Sent ${name} back to ${step}.` : `Sent ${name} back.`;
  // The version it was recorded against: "at abc1234" when the request named
  // it, "(recorded at abc1234)" when it did not.
  const recorded = recordedWords(result?.version, result?.version_named);
  if (recorded) name = `${name} ${recorded}`;
  if (!step) return `Approved ${name}.`;
  if (result?.held) return `Approved ${name}. It goes on with ${step} on Resume.`;
  return result?.engine_resident
    ? `Approved ${name}. Foreman goes on with ${step}.`
    : `Approved ${name}. It waits at ${step} until a worker runs.`;
}
