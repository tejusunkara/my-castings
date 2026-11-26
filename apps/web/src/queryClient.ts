import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";

import { SESSION_QUERY_KEY } from "./api/auth";
import { ApiError, isUnauthorized } from "./api/client";

/** A 401 from any request means the session expired: flip the session flag, and
 * ProtectedRoute sends the user to /login. */
export function createQueryClient(): QueryClient {
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: onUnauthorized }),
    mutationCache: new MutationCache({ onError: onUnauthorized }),
    defaultOptions: {
      queries: {
        // Retry network and server errors; a 4xx answer won't change on a retry.
        retry: (failures, error) =>
          !(error instanceof ApiError && error.status < 500) && failures < 2,
        refetchOnWindowFocus: true,
      },
    },
  });

  function onUnauthorized(error: unknown) {
    if (isUnauthorized(error)) client.setQueryData(SESSION_QUERY_KEY, false);
  }

  return client;
}
