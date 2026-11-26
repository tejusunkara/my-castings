import { describe, expect, it } from "vitest";

import { formatAges, formatDeadline, formatLocations } from "./format";

describe("formatAges", () => {
  it.each([
    [21, 29, "21–29"],
    [18, null, "18+"],
    [25, 25, "25"],
    [null, 40, "up to 40"],
    [null, null, null],
  ])("%s–%s → %s", (age_min, age_max, expected) => {
    expect(formatAges({ age_min, age_max })).toBe(expected);
  });
});

describe("formatLocations", () => {
  it("shows the first and a count of the rest", () => {
    expect(formatLocations(["Brooklyn, NY", "Queens, NY", "Remote"])).toBe("Brooklyn, NY +2 more");
    expect(formatLocations(["Remote"])).toBe("Remote");
    expect(formatLocations([])).toBeNull();
  });
});

describe("formatDeadline", () => {
  const now = new Date("2026-11-26T12:00:00Z");

  it("shows open deadlines as a date", () => {
    const d = formatDeadline("2026-11-29T17:00:00Z", now);
    expect(d.closed).toBe(false);
    expect(d.text).toMatch(/Nov 29/);
    expect(d.full).toMatch(/2026/);
  });

  it("marks past deadlines closed", () => {
    const d = formatDeadline("2026-11-20T17:00:00Z", now);
    expect(d).toMatchObject({ closed: true });
    expect(d.text).toMatch(/^Closed Nov 20/);
  });

  it("adds the year when it isn't this year", () => {
    expect(formatDeadline("2027-01-05T17:00:00Z", now).text).toMatch(/2027/);
  });

  it("handles a missing deadline", () => {
    expect(formatDeadline(null, now)).toEqual({ text: "Not listed", full: null, closed: false });
  });
});
