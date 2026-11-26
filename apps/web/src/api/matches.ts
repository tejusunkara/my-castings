import { request } from "./client";
import type { Match, MatchSort, MatchStatus, MatchSummary } from "./types";

export interface MatchFilters {
  statuses: MatchStatus[];
  // null = every source. An empty list means none, which callers handle by not asking.
  sources: string[] | null;
  projectType: string;
  q: string;
}

export const PAGE_SIZE = 100;

function filterQuery(filters: Omit<MatchFilters, "statuses">) {
  return {
    source: filters.sources ?? undefined,
    project_type: filters.projectType || undefined,
    q: filters.q.trim() || undefined,
  };
}

export const listMatches = (filters: MatchFilters, sort: MatchSort, offset: number) =>
  request<Match[]>("GET", "/matches", {
    query: {
      ...filterQuery(filters),
      status: filters.statuses,
      sort,
      limit: PAGE_SIZE,
      offset,
    },
  });

export const getMatchSummary = (filters: Omit<MatchFilters, "statuses">) =>
  request<MatchSummary>("GET", "/matches/summary", { query: filterQuery(filters) });

export interface MatchPatch {
  status?: MatchStatus;
  user_note?: string | null;
}

export const updateMatch = (id: number, patch: MatchPatch) =>
  request<Match>("PATCH", `/matches/${id}`, { body: patch });
