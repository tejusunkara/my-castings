import { useMutation, useQueryClient, type InfiniteData } from "@tanstack/react-query";

import { updateMatch, type MatchPatch } from "../api/matches";
import type { CastingCall, Match } from "../api/types";

/**
 * Changes a match's status or note. The new value shows at once in every cached list and
 * casting call; afterwards everything under "matches" and "casting-call" is refetched so
 * counts and filters settle on the server's answer.
 */
export function useUpdateMatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: MatchPatch }) => updateMatch(id, patch),
    onMutate: async ({ id, patch }) => {
      await queryClient.cancelQueries({ queryKey: ["matches", "list"] });
      queryClient.setQueriesData<InfiniteData<Match[]>>(
        { queryKey: ["matches", "list"] },
        (data) =>
          data && {
            ...data,
            pages: data.pages.map((page) =>
              page.map((m) => (m.id === id ? { ...m, ...patch } : m)),
            ),
          },
      );
      queryClient.setQueriesData<CastingCall>(
        { queryKey: ["casting-call"] },
        (call) =>
          call && {
            ...call,
            roles: call.roles.map((r) =>
              r.saved_match?.id === id ? { ...r, saved_match: { ...r.saved_match, ...patch } } : r,
            ),
          },
      );
    },
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ["matches"] }),
        queryClient.invalidateQueries({ queryKey: ["casting-call"] }),
      ]),
  });
}
