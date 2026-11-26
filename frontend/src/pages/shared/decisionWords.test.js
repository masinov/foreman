import { decisionSentence, taskName } from "./decisionWords";

describe("decisionSentence", () => {
  it("says an approval with the engine running", () => {
    expect(decisionSentence("FOR-51", { next_step: "merge", engine_resident: true })).toBe(
      "Approved FOR-51. Foreman goes on with Merge.",
    );
  });

  it("says where a task waits when no engine runs", () => {
    expect(decisionSentence("FOR-51", { next_step: "merge", engine_resident: false })).toBe(
      "Approved FOR-51. It waits at Merge until a worker runs.",
    );
  });

  it("says a held task goes on when resumed (ADR-0043)", () => {
    expect(decisionSentence("FOR-51", { next_step: "merge", engine_resident: true, held: true })).toBe(
      "Approved FOR-51. It goes on with Merge on Resume.",
    );
  });

  it("names the step as Activity does, never the raw id", () => {
    expect(decisionSentence("FOR-51", { next_step: "code_review", engine_resident: true })).not.toMatch(/[`_]/);
  });

  it("says a send-back, and falls back without the next step", () => {
    expect(decisionSentence("FOR-51", { next_step: "develop" }, { sentBack: true })).toBe("Sent FOR-51 back to Develop.");
    expect(decisionSentence("FOR-51", {})).toBe("Approved FOR-51.");
    expect(decisionSentence("FOR-51", {}, { sentBack: true })).toBe("Sent FOR-51 back.");
  });

  it("names a task by its key, else its title", () => {
    expect(taskName({ task_key: "FOR-1", title: "T" })).toBe("FOR-1");
    expect(taskName({ title: "T" })).toBe("T");
    expect(taskName({ task_title: "U" })).toBe("U");
  });
});
