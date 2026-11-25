import { describe, expect, it } from "vitest";

import { readsWords, stepFacts } from "./stepFacts";

const run = { id: "r1", role_id: "developer", workflow_step: "develop", status: "completed", outcome: "done", cost_usd: 0.09, tokens: 3500 };
const facts = (repo) => stepFacts(run, [], { repo });
const fact = (list, key) => list.find((entry) => entry.key === key);

describe("a step's facts: reads before its first edit and tokens", () => {
  it("says how many reads came before the first edit", () => {
    expect(fact(facts({ reads: { reads: 7, edited: true } }), "reads")).toMatchObject({ term: "Reads", text: "7 reads before its first edit" });
    expect(readsWords({ reads: 1, edited: true })).toBe("1 read before its first edit");
  });

  it("says 'no edit' for a step that changed nothing", () => {
    expect(fact(facts({ reads: { reads: 4, edited: false } }), "reads").text).toBe("4 reads, no edit");
    expect(fact(facts({ reads: { reads: 0, edited: false } }), "reads").text).toBe("0 reads, no edit");
  });

  it("adds nothing for an older step that did not record its reads", () => {
    expect(fact(facts(null), "reads")).toBeUndefined();
    expect(fact(facts({ reads: null }), "reads")).toBeUndefined();
  });

  it("keeps the tokens the step used beside its cost", () => {
    expect(fact(facts({ reads: { reads: 7, edited: true } }), "spend").spend).toEqual({ amount: 0.09, tokens: 3500 });
  });
});
