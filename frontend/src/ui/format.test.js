import { formatDay, formatDuration, formatMoney, humanize, plural, shortSha, splitTitle } from "./format";

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

describe("dates and titles", () => {
  it("formats a day, with the year only when it is another year", () => {
    const now = new Date("2026-11-12T12:00:00Z");
    expect(formatDay("2026-11-11T12:00:00Z", now)).toBe("11 Nov");
    expect(formatDay("2025-03-02T12:00:00Z", now)).toBe("2 Mar 2025");
    expect(formatDay(null, now)).toBe("");
    expect(formatDay("not a date", now)).toBe("");
  });

  it("splits a sprint title at its first colon", () => {
    expect(splitTitle("Sprint 55: baseline and host safety")).toEqual(["Sprint 55", "baseline and host safety"]);
    expect(splitTitle("Later")).toEqual(["Later", ""]);
    expect(splitTitle(": odd")).toEqual([": odd", ""]);
  });
});

describe("formatDuration", () => {
  it("says seconds to ten minutes, then minutes, then hours", () => {
    expect(formatDuration(null)).toBe("");
    expect(formatDuration(7)).toBe("7 s");
    expect(formatDuration(114.24)).toBe("114.2 s");
    expect(formatDuration(840)).toBe("14 min");
    expect(formatDuration(7500)).toBe("2 h 5 min");
    expect(formatDuration(7200)).toBe("2 h");
  });
});
