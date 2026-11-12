import { formatMoney, humanize, plural, shortSha } from "./format";

describe("format", () => {
  it("formats amounts, identifiers and shas", () => {
    expect(formatMoney(1.314)).toBe("$1.31");
    expect(formatMoney(undefined)).toBe("$0.00");
    expect(humanize("merge_approval")).toBe("Merge approval");
    expect(humanize("")).toBe("");
    expect(shortSha("b232eb1aa0")).toBe("b232eb1");
    expect(plural(1, "task")).toBe("1 task");
    expect(plural(2, "task")).toBe("2 tasks");
  });
});
