// Mirrors apps/api/app/schemas. Datetimes arrive as ISO 8601 strings.

export const MATCH_STATUSES = ["new", "saved", "applied", "dismissed"] as const;
export type MatchStatus = (typeof MATCH_STATUSES)[number];

export const MATCH_SORTS = ["deadline", "matched", "posted"] as const;
export type MatchSort = (typeof MATCH_SORTS)[number];

export interface Role {
  id: number;
  role_name: string;
  billing_type: string | null;
  genders: string[];
  age_min: number | null;
  age_max: number | null;
  is_featured: boolean;
  pay: string | null;
  // Personal to the artist's account on the source site: open it, never share it.
  apply_url: string | null;
}

export interface CastingCallSummary {
  id: number;
  source_key: string;
  title: string;
  category_tag: string | null;
  project_type: string | null;
  union_status: string | null;
  posted_at: string | null;
  submission_deadline: string | null;
  seeking_locations: string[];
  is_featured: boolean;
  view_all_jobs_url: string | null;
}

export interface Match {
  id: number;
  status: MatchStatus;
  matched_at: string;
  match_reasons: Record<string, boolean>;
  user_note: string | null;
  applied_at: string | null;
  role: Role;
  casting_call: CastingCallSummary;
}

export interface Source {
  key: string;
  display_name: string;
}

export interface MatchSummary {
  status_counts: Record<MatchStatus, number>;
  project_types: string[];
  sources: Source[];
}
