import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Navigate } from "react-router";

import { hasSession, SESSION_QUERY_KEY } from "../../api/auth";

/** Renders children when logged in; sends everyone else to /login. */
export function ProtectedRoute({ children }: { children: ReactNode }) {
  const session = useQuery({ queryKey: SESSION_QUERY_KEY, queryFn: hasSession, staleTime: Infinity });

  if (session.isPending) return null;
  if (session.isError) {
    return (
      <p role="alert" style={{ padding: 32 }}>
        Can’t reach the API: {session.error.message}
      </p>
    );
  }
  return session.data ? children : <Navigate to="/login" replace />;
}
