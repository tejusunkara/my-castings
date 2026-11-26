import { describe, expect, it } from "vitest";

import { DEFAULT_SORT, DEFAULT_STATUSES, readState, toggle, writeState } from "./filters";

describe("dashboard URL state", () => {
  it("uses defaults when the URL is empty", () => {
    const state = readState(new URLSearchParams());
    expect(state.filters).toEqual({
      statuses: DEFAULT_STATUSES,
      sources: null,
      projectType: "",
      q: "",
    });
    expect(state.sort).toBe(DEFAULT_SORT);
    expect(writeState(state).toString()).toBe("");
  });

  it("round-trips every field", () => {
    const params = new URLSearchParams(
      "status=saved,dismissed&sources=backstage&type=Commercial&q=nyc&sort=posted",
    );
    const state = readState(params);
    expect(state.filters).toEqual({
      statuses: ["saved", "dismissed"],
      sources: ["backstage"],
      projectType: "Commercial",
      q: "nyc",
    });
    expect(readState(writeState(state))).toEqual(state);
  });

  it("keeps 'none selected' distinct from 'default'", () => {
    const state = readState(new URLSearchParams("status=&sources="));
    expect(state.filters.statuses).toEqual([]);
    expect(state.filters.sources).toEqual([]);
    expect(readState(writeState(state))).toEqual(state);
  });

  it("ignores unknown values", () => {
    const state = readState(new URLSearchParams("status=new,bogus&sort=random"));
    expect(state.filters.statuses).toEqual(["new"]);
    expect(state.sort).toBe(DEFAULT_SORT);
  });

  it("toggle adds and removes", () => {
    expect(toggle(["a", "b"], "a")).toEqual(["b"]);
    expect(toggle(["b"], "a")).toEqual(["b", "a"]);
  });
});
