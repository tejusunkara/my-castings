import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";

import { getMatchSummary, listMatches, PAGE_SIZE, updateMatchStatus } from "../api/matches";
import type { Match, MatchSort, MatchStatus } from "../api/types";
import { AppHeader } from "../components/layout/AppHeader";
import { FiltersPanel } from "../components/matches/FiltersPanel";
import { MatchCard } from "../components/matches/MatchCard";
import { StatusTiles } from "../components/matches/StatusTiles";
import { readState, toggle, writeState, type DashboardState } from "../lib/filters";
import styles from "./DashboardPage.module.css";

const SORT_LABELS: Record<MatchSort, string> = {
  deadline: "Deadline soonest",
  matched: "Newest matches",
  posted: "Recently posted",
};

const SEARCH_DELAY_MS = 250;

export function DashboardPage() {
  const [params, setParams] = useSearchParams();
  const state = readState(params);
  const { filters, sort } = state;
  const queryClient = useQueryClient();

  const update = (patch: Partial<DashboardState["filters"]> & { sort?: MatchSort }) => {
    const { sort: nextSort = sort, ...filterPatch } = patch;
    setParams(writeState({ filters: { ...filters, ...filterPatch }, sort: nextSort }), {
      replace: true,
    });
  };

  // The search box updates the URL (and so the query) once typing pauses.
  const [search, setSearch] = useState(filters.q);
  useEffect(() => {
    if (search === filters.q) return;
    const timer = setTimeout(() => update({ q: search }), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only typing should trigger this
  }, [search]);

  const summaryFilters = { sources: filters.sources, projectType: filters.projectType, q: filters.q };
  const summary = useQuery({
    queryKey: ["matches", "summary", summaryFilters],
    queryFn: () => getMatchSummary(summaryFilters),
    placeholderData: keepPreviousData,
  });

  const nothingSelected =
    filters.statuses.length === 0 || (filters.sources !== null && filters.sources.length === 0);
  const list = useInfiniteQuery({
    queryKey: ["matches", "list", filters, sort],
    queryFn: ({ pageParam }) => listMatches(filters, sort, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last, pages) =>
      last.length === PAGE_SIZE ? pages.length * PAGE_SIZE : undefined,
    enabled: !nothingSelected,
    placeholderData: keepPreviousData,
  });

  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: MatchStatus }) =>
      updateMatchStatus(id, status),
    // Show the new status right away; the refetch afterwards settles counts and filters.
    onMutate: async ({ id, status }) => {
      await queryClient.cancelQueries({ queryKey: ["matches", "list"] });
      queryClient.setQueriesData<InfiniteData<Match[]>>(
        { queryKey: ["matches", "list"] },
        (data) =>
          data && {
            ...data,
            pages: data.pages.map((page) => page.map((m) => (m.id === id ? { ...m, status } : m))),
          },
      );
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["matches"] }),
  });

  const matches = nothingSelected ? [] : (list.data?.pages.flat() ?? []);
  const shownTotal = summary.data
    ? filters.statuses.reduce((sum, s) => sum + summary.data.status_counts[s], 0)
    : null;

  return (
    <>
      <AppHeader />
      <main className={styles.layout}>
        <aside className={styles.sidebar}>
          <StatusTiles
            counts={summary.data?.status_counts}
            selected={filters.statuses}
            onToggle={(status) => update({ statuses: toggle(filters.statuses, status) })}
          />
          <FiltersPanel
            search={search}
            onSearchChange={setSearch}
            sources={summary.data?.sources ?? []}
            selectedSources={filters.sources}
            onSourcesChange={(sources) => update({ sources })}
            projectTypes={summary.data?.project_types ?? []}
            projectType={filters.projectType}
            onProjectTypeChange={(projectType) => update({ projectType })}
          />
        </aside>

        <section className={styles.results} aria-labelledby="results-count">
          <div className={styles.toolbar}>
            <p id="results-count" className={styles.count} aria-live="polite">
              {shownTotal === null ? "Loading…" : `${shownTotal} ${shownTotal === 1 ? "role" : "roles"}`}
            </p>
            <label className="visually-hidden" htmlFor="sort">
              Sort
            </label>
            <select
              id="sort"
              className={styles.sort}
              value={sort}
              onChange={(e) => update({ sort: e.target.value as MatchSort })}
            >
              {Object.entries(SORT_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  Sort: {label}
                </option>
              ))}
            </select>
          </div>

          {setStatus.isError && (
            <p role="alert" className={styles.notice}>
              Couldn’t update the status: {setStatus.error.message}
            </p>
          )}

          {nothingSelected ? (
            <p className={styles.notice}>
              {filters.statuses.length === 0
                ? "Pick at least one status on the left to see roles."
                : "Pick at least one source to see roles."}
            </p>
          ) : list.isError ? (
            <p role="alert" className={styles.notice}>
              Couldn’t load roles: {list.error.message}{" "}
              <button type="button" className={styles.linkButton} onClick={() => list.refetch()}>
                Try again
              </button>
            </p>
          ) : list.isPending ? (
            <p className={styles.notice}>Loading roles…</p>
          ) : matches.length === 0 ? (
            <p className={styles.notice}>
              No roles match these filters.{" "}
              <button
                type="button"
                className={styles.linkButton}
                onClick={() => {
                  setSearch("");
                  setParams(new URLSearchParams(), { replace: true });
                }}
              >
                Clear filters
              </button>
            </p>
          ) : (
            <div className={styles.grid} aria-busy={list.isFetching}>
              {matches.map((match) => (
                <MatchCard
                  key={match.id}
                  match={match}
                  updating={setStatus.isPending && setStatus.variables?.id === match.id}
                  onStatusChange={(status) => setStatus.mutate({ id: match.id, status })}
                />
              ))}
            </div>
          )}

          {list.hasNextPage && !nothingSelected && (
            <button
              type="button"
              className={styles.more}
              onClick={() => list.fetchNextPage()}
              disabled={list.isFetchingNextPage}
            >
              {list.isFetchingNextPage ? "Loading…" : "Load more"}
            </button>
          )}
        </section>
      </main>
    </>
  );
}
