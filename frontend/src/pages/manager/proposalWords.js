// A proposal in plain words: what it will create, change and leave, one row
// per thing, each under a short verb. Consecutive rows under the same verb
// show it once (design: 06-manager-open.html, 05-task-overview.html).
//
// A row is `{ term, task?, text?, quiet? }`: `task` is `{ key, title }` from
// the proposal's `names` (as they were when it was proposed), `text` the
// words, `quiet` for what is said in a secondary colour (what is left). A row
// in a list of tasks (planned in, left) names the task by its title alone;
// a row acting on one task leads with its key.

import { humanize } from "../../ui/format";

const TASK_FIELDS = {
  title: "title",
  task_type: "type",
  description: "description",
  acceptance_criteria: "acceptance criteria",
  priority: "priority",
};

function taskOf(names, taskId) {
  const known = names?.tasks?.[taskId];
  return { key: known?.key || taskId, title: known?.title || "" };
}

// What a gate decides, by its policy, as the object of "approve".
const GATE_OBJECTS = { merge_approval: "the merge", plan_approval: "the plan" };

function gateObject(gate) {
  return GATE_OBJECTS[gate.policy] || humanize(gate.step).toLowerCase();
}

/** Where a task waiting at a gate goes, from the proposal's names; null when unknown. */
function gateOf(names, taskId) {
  return names?.tasks?.[taskId]?.gate || null;
}

/** A task in a list: its title, or its key when no title is known. */
function listed(names, taskId) {
  const task = taskOf(names, taskId);
  return task.title ? { text: task.title } : { task };
}

function sprintTitle(names, sprintId) {
  return names?.sprints?.[sprintId]?.title || sprintId;
}

function list(words) {
  if (words.length <= 1) return words.join("");
  return `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;
}

function rowsOf(operation, names) {
  const task = operation.task_id ? taskOf(names, operation.task_id) : null;
  const sprint = operation.sprint_id ? sprintTitle(names, operation.sprint_id) : null;
  switch (operation.kind) {
    case "create_sprint":
      return [{ term: "Create", text: `${operation.title}, planned` }];
    case "edit_sprint": {
      const rows = [];
      if (operation.title !== undefined) rows.push({ term: "Rename", text: `${sprint} to ${operation.title}` });
      if (operation.goal !== undefined)
        rows.push({ term: "Goal", text: operation.goal ? `${sprint}: ${operation.goal}` : `${sprint}: no goal` });
      return rows;
    }
    case "activate_sprint":
      return [{ term: "Start", text: sprint }];
    case "finish_sprint":
      return [{ term: "Finish", text: sprint }];
    case "file_task":
      return [{ term: "File", text: `${operation.title}, ${operation.accept ? "accepted" : "in the backlog"}` }];
    case "accept_task":
      return [{ term: "Accept", task }];
    case "decline_task":
      return [{ term: "Decline", task }, ...(operation.reason ? [{ term: "Why", text: operation.reason }] : [])];
    case "plan_tasks": {
      const rows = [];
      if (operation.new_sprint) rows.push({ term: "Create", text: `${operation.new_sprint.title}, planned` });
      else rows.push({ term: "Into", text: sprintTitle(names, operation.sprint_id) });
      for (const taskId of operation.task_ids || []) rows.push({ term: "Plan in", ...listed(names, taskId) });
      return rows;
    }
    case "unplan_task":
      return [{ term: "Move back", task, text: "to the backlog" }];
    case "edit_task": {
      const fields = Object.keys(TASK_FIELDS).filter((name) => operation[name] !== undefined);
      const rows = [{ term: "Change", task, text: `its ${list(fields.map((name) => TASK_FIELDS[name]))}` }];
      if (operation.title !== undefined) rows.push({ term: "Title", text: operation.title });
      return rows;
    }
    case "block_task":
      return [{ term: "Block", task }, { term: "Why", text: operation.reason }];
    case "unblock_task":
      return [{ term: "Unblock", task }];
    case "cancel_task":
      return [{ term: "Cancel", task }];
    case "send_back": {
      const gate = gateOf(names, operation.task_id);
      const where = gate?.deny_to ? `to ${humanize(gate.deny_to)}, in place of approving ${gateObject(gate)}` : "";
      return [{ term: "Send back", task: { key: task.key, title: "" }, text: where || task.title }, { term: "Guidance", text: operation.guidance }];
    }
    case "approve_gate": {
      const gate = gateOf(names, operation.task_id);
      const rows = [{ term: "Approve", task: { key: task.key, title: "" }, text: gate ? gateObject(gate) : task.title }];
      if (gate?.approve_to) rows.push({ term: "Then", text: `${humanize(gate.approve_to)}, when the engine runs` });
      return rows;
    }
    default:
      return [{ term: "Change", text: String(operation.kind || "") }];
  }
}

/** Every row of a proposal, in order, with repeated verbs shown once. */
export function proposalRows(proposal) {
  const rows = [];
  for (const operation of proposal?.operations || []) rows.push(...rowsOf(operation, proposal.names));
  for (const taskId of proposal?.leaves || []) rows.push({ term: "Leave", ...listed(proposal.names, taskId), quiet: true });
  return rows.map((row, index) => ({ ...row, term: index > 0 && rows[index - 1].term === row.term ? "" : row.term }));
}

/** The card's first line: what the person is looking at. */
export function proposalHeading(proposal) {
  if (proposal?.state === "proposed") return "Proposed change. Nothing happens until you confirm.";
  return "Proposed change.";
}

/**
 * What happened to a decided proposal, as a sentence, and its tone:
 * `applied`, `declined` or `failed`. Null while it waits.
 */
export function proposalOutcome(proposal) {
  if (!proposal || proposal.state === "proposed") return null;
  const by = proposal.decided_by ? ` by ${proposal.decided_by}` : "";
  const sentence = proposal.outcome?.sentence || "";
  if (proposal.state === "confirmed") return { tone: "applied", text: `Confirmed${by}. ${sentence || "Applied."}`.trim() };
  if (proposal.state === "declined") return { tone: "declined", text: `Declined${by}. Nothing was changed.` };
  return { tone: "failed", text: `Not applied. ${sentence}`.trim() };
}
