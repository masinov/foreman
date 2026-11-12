import { proposalHeading, proposalOutcome, proposalRows } from "./proposalWords";

const names = {
  tasks: {
    t1: { key: "FOR-1", title: "One" },
    t2: { key: "FOR-2", title: "Two" },
  },
  sprints: { s1: { title: "Sprint 1" }, s2: { title: "Sprint 2" } },
};

const rows = (operations, leaves = []) =>
  proposalRows({ operations, leaves, names }).map(({ term, task, text, quiet }) => [term, task ? `${task.key} ${task.title}` : null, text ?? null, Boolean(quiet)]);

describe("a proposal in words", () => {
  it.each([
    [{ kind: "create_sprint", title: "Sprint 3" }, [["Create", null, "Sprint 3, planned", false]]],
    [{ kind: "edit_sprint", sprint_id: "s2", title: "Two", goal: "" }, [["Rename", null, "Sprint 2 to Two", false], ["Goal", null, "Sprint 2: no goal", false]]],
    [{ kind: "activate_sprint", sprint_id: "s2" }, [["Start", null, "Sprint 2", false]]],
    [{ kind: "finish_sprint", sprint_id: "s1" }, [["Finish", null, "Sprint 1", false]]],
    [{ kind: "file_task", title: "New", accept: true }, [["File", null, "New, accepted", false]]],
    [{ kind: "file_task", title: "New" }, [["File", null, "New, in the backlog", false]]],
    [{ kind: "accept_task", task_id: "t1" }, [["Accept", "FOR-1 One", null, false]]],
    [{ kind: "decline_task", task_id: "t1", reason: "No." }, [["Decline", "FOR-1 One", null, false], ["Why", null, "No.", false]]],
    [{ kind: "plan_tasks", task_ids: ["t1", "t2"], sprint_id: "s2" }, [["Into", null, "Sprint 2", false], ["Plan in", "FOR-1 One", null, false], ["", "FOR-2 Two", null, false]]],
    [{ kind: "unplan_task", task_id: "t1" }, [["Move back", "FOR-1 One", "to the backlog", false]]],
    [{ kind: "edit_task", task_id: "t1", title: "Uno", priority: 1 }, [["Change", "FOR-1 One", "its title and priority", false], ["Title", null, "Uno", false]]],
    [{ kind: "block_task", task_id: "t1", reason: "Wait." }, [["Block", "FOR-1 One", null, false], ["Why", null, "Wait.", false]]],
    [{ kind: "unblock_task", task_id: "t1" }, [["Unblock", "FOR-1 One", null, false]]],
    [{ kind: "cancel_task", task_id: "t1" }, [["Cancel", "FOR-1 One", null, false]]],
    [{ kind: "send_back", task_id: "t1", guidance: "More tests." }, [["Send back", "FOR-1 One", null, false], ["Guidance", null, "More tests.", false]]],
    [{ kind: "approve_gate", task_id: "t1" }, [["Approve", "FOR-1 One", null, false]]],
  ])("says %j", (operation, expected) => {
    expect(rows([operation])).toEqual(expected);
  });

  it("says what it leaves, quietly, and repeats a verb only once", () => {
    expect(rows([{ kind: "cancel_task", task_id: "t1" }, { kind: "cancel_task", task_id: "t2" }], ["t1"])).toEqual([
      ["Cancel", "FOR-1 One", null, false],
      ["", "FOR-2 Two", null, false],
      ["Leave", "FOR-1 One", null, true],
    ]);
  });

  it("falls back to the id when a task was not named", () => {
    expect(proposalRows({ operations: [{ kind: "accept_task", task_id: "ghost" }], names: {} })[0].task).toEqual({ key: "ghost", title: "" });
  });

  it("heads and closes by state", () => {
    expect(proposalHeading({ state: "proposed" })).toBe("Proposed change. Nothing happens until you confirm.");
    expect(proposalHeading({ state: "confirmed" })).toBe("Proposed change.");
    expect(proposalOutcome({ state: "proposed" })).toBeNull();
    expect(proposalOutcome({ state: "confirmed", decided_by: "ada", outcome: { sentence: "Applied 1 operation." } })).toEqual({ tone: "applied", text: "Confirmed by ada. Applied 1 operation." });
    expect(proposalOutcome({ state: "declined", decided_by: null })).toEqual({ tone: "declined", text: "Declined. Nothing was changed." });
    expect(proposalOutcome({ state: "failed", outcome: { sentence: "Operation 1 of 1 was refused: x. Nothing was applied." } })).toEqual({
      tone: "failed",
      text: "Not applied. Operation 1 of 1 was refused: x. Nothing was applied.",
    });
  });
});
