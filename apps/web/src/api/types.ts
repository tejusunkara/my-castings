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

export interface RoleMatch {
  id: number;
  status: MatchStatus;
  user_note: string | null;
  applied_at: string | null;
}

export interface RoleDetail extends Role {
  saved_match: RoleMatch | null; // null when the role didn't match the profile
}

export interface CastingCall extends CastingCallSummary {
  description: string | null;
  roles: RoleDetail[];
}

export interface Profile {
  id: number;
  updated_at: string;
  display_name: string | null;
  date_of_birth: string | null; // YYYY-MM-DD
  playing_age_min: number | null;
  playing_age_max: number | null;
  genders: string[];
  location_city: string | null;
  location_state: string | null;
  union_status: string | null;
  bio: string | null;
  willing_to_travel: boolean;
}

export type ProfileInput = Omit<Profile, "id" | "updated_at">;

export const PARSE_STATUSES = ["pending", "success", "partial", "failed"] as const;
export type ParseStatus = (typeof PARSE_STATUSES)[number];

export interface RawEmail {
  id: number;
  s3_bucket: string;
  s3_key: string;
  received_at: string;
  subject: string | null;
  from_address: string | null;
  source_key: string | null;
  sender_verified: boolean;
  verdict_details: Record<string, unknown> | null;
  parse_status: ParseStatus;
  parse_error: string | null;
  parsed_at: string | null;
}

export interface ReprocessResult {
  raw_email: RawEmail;
  created_roles: number;
  updated_roles: number;
  deleted_roles: number;
  kept_role_ids: number[];
  new_matches: number;
}

export const ASSET_TYPES = [
  "headshot",
  "digital",
  "acting_reel",
  "self_tape",
  "resume",
  "social_link",
] as const;
export type AssetType = (typeof ASSET_TYPES)[number];

export interface MediaAsset {
  id: number;
  asset_type: AssetType;
  label: string | null;
  is_current: boolean;
  upload_status: "pending" | "completed";
  content_type: string | null;
  file_size_bytes: number | null;
  original_filename: string | null;
  external_url: string | null;
  created_at: string;
  completed_at: string | null;
  view_url: string | null; // signed, valid for an hour
}

export interface UploadStarted {
  asset: MediaAsset;
  upload: { url: string; fields: Record<string, string> };
}
