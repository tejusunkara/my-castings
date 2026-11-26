import type { CastingCallSummary, Match, MatchSummary, Role } from "../api/types";

type MatchOverrides = Partial<Omit<Match, "role" | "casting_call">> & {
  id: number;
  role?: Partial<Role>;
  casting_call?: Partial<CastingCallSummary>;
};

export function makeMatch(overrides: MatchOverrides): Match {
  return {
    status: "new",
    matched_at: "2026-11-20T12:00:00Z",
    match_reasons: { age: true, gender: true, location: true },
    user_note: null,
    applied_at: null,
    ...overrides,
    role: {
      id: overrides.id * 10,
      role_name: "Lead Girl",
      billing_type: null,
      genders: ["female"],
      age_min: 21,
      age_max: 29,
      is_featured: false,
      pay: "$850 for 9 hours of work",
      apply_url: "https://example.com/apply?token=secret",
      ...overrides.role,
    },
    casting_call: {
      id: overrides.id * 100,
      source_key: "backstage",
      title: "Bright Side Soda",
      category_tag: null,
      project_type: "Commercial",
      union_status: "nonunion",
      posted_at: null,
      submission_deadline: "2099-12-01T17:00:00Z",
      seeking_locations: ["New York, NY"],
      is_featured: false,
      view_all_jobs_url: null,
      ...overrides.casting_call,
    },
  };
}

export const SUMMARY: MatchSummary = {
  status_counts: { new: 2, saved: 1, applied: 0, dismissed: 3 },
  project_types: ["Commercial", "Web Series"],
  sources: [
    { key: "actors_access", display_name: "Actors Access" },
    { key: "backstage", display_name: "Backstage" },
    { key: "casting_networks", display_name: "Casting Networks" },
  ],
};
