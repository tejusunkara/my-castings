import type {
  CastingCall,
  CastingCallSummary,
  Match,
  MatchSummary,
  Profile,
  RawEmail,
  Role,
} from "../api/types";

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

export function makeCastingCall(overrides: Partial<CastingCall> = {}): CastingCall {
  return {
    id: 100,
    source_key: "backstage",
    title: "Bright Side Soda",
    category_tag: "Commercial · $ Paid · Nonunion",
    project_type: "Commercial",
    union_status: "nonunion",
    posted_at: "2026-11-24T15:00:00Z",
    submission_deadline: "2099-12-01T17:00:00Z",
    seeking_locations: ["New York, NY", "Brooklyn, NY"],
    is_featured: false,
    view_all_jobs_url: "https://example.com/job",
    description: "A fizzy spot for a new soda.",
    roles: [
      {
        id: 10,
        role_name: "Lead Girl",
        billing_type: "Lead",
        genders: ["female"],
        age_min: 21,
        age_max: 29,
        is_featured: false,
        pay: "$850 for 9 hours of work",
        apply_url: "https://example.com/apply?token=secret",
        saved_match: { id: 1, status: "new", user_note: null, applied_at: null },
      },
      {
        id: 11,
        role_name: "Dad",
        billing_type: "Supporting",
        genders: ["male"],
        age_min: 40,
        age_max: 55,
        is_featured: false,
        pay: null,
        apply_url: null,
        saved_match: null,
      },
    ],
    ...overrides,
  };
}

export function makeProfile(overrides: Partial<Profile> = {}): Profile {
  return {
    id: 1,
    updated_at: "2026-11-20T12:00:00Z",
    display_name: "Ana",
    date_of_birth: null,
    playing_age_min: 16,
    playing_age_max: 30,
    genders: ["female", "any gender", "femme presenting"],
    location_city: "New York City",
    location_state: "NY",
    union_status: null,
    bio: null,
    willing_to_travel: true,
    ...overrides,
  };
}

export function makeRawEmail(overrides: Partial<RawEmail> = {}): RawEmail {
  return {
    id: 7,
    s3_bucket: "local",
    s3_key: "digest.eml",
    received_at: "2026-11-25T18:13:00Z",
    subject: "Fwd: Projects match your profile",
    from_address: "redacted@gmail.com",
    source_key: null,
    sender_verified: true,
    verdict_details: { verified_by: "dkim", from_domain: "gmail.com" },
    parse_status: "failed",
    parse_error: "no adapter for sender 'redacted@gmail.com'",
    parsed_at: "2026-11-25T18:14:00Z",
    ...overrides,
  };
}
