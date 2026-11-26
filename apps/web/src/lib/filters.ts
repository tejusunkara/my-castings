/**
 * Dashboard filters and sort live in the URL (?status=new,saved&sources=backstage&...),
 * so a refresh or a bookmark brings back the same view.
 *
 * A missing parameter means the default; a present-but-empty one means "none selected".
 */
import type { MatchFilters } from "../api/matches";
import { MATCH_SORTS, MATCH_STATUSES, type MatchSort, type MatchStatus } from "../api/types";

// Dismissed roles stay out of the way unless asked for.
export const DEFAULT_STATUSES: MatchStatus[] = ["new", "saved", "applied"];
export const DEFAULT_SORT: MatchSort = "deadline";

export interface DashboardState {
  filters: MatchFilters;
  sort: MatchSort;
}

function list(params: URLSearchParams, key: string): string[] | null {
  const value = params.get(key);
  if (value === null) return null;
  return value.split(",").filter(Boolean);
}

export function readState(params: URLSearchParams): DashboardState {
  const statuses = list(params, "status");
  const sort = params.get("sort");
  return {
    filters: {
      statuses:
        statuses === null ? DEFAULT_STATUSES : MATCH_STATUSES.filter((s) => statuses.includes(s)),
      sources: list(params, "sources"),
      projectType: params.get("type") ?? "",
      q: params.get("q") ?? "",
    },
    sort: MATCH_SORTS.includes(sort as MatchSort) ? (sort as MatchSort) : DEFAULT_SORT,
  };
}

export function writeState({ filters, sort }: DashboardState): URLSearchParams {
  const params = new URLSearchParams();
  const sameAsDefault =
    filters.statuses.length === DEFAULT_STATUSES.length &&
    DEFAULT_STATUSES.every((s) => filters.statuses.includes(s));
  if (!sameAsDefault) params.set("status", filters.statuses.join(","));
  if (filters.sources !== null) params.set("sources", filters.sources.join(","));
  if (filters.projectType) params.set("type", filters.projectType);
  if (filters.q) params.set("q", filters.q);
  if (sort !== DEFAULT_SORT) params.set("sort", sort);
  return params;
}

export function toggle<T>(items: readonly T[], item: T): T[] {
  return items.includes(item) ? items.filter((i) => i !== item) : [...items, item];
}
