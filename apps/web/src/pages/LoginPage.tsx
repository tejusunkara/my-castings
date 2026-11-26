import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router";

import { hasSession, login, SESSION_QUERY_KEY } from "../api/auth";
import { ApiError } from "../api/client";
import { Logo } from "../components/layout/AppHeader";
import styles from "./LoginPage.module.css";

function loginError(error: Error): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "That password isn’t right.";
    if (error.status === 429) return "Too many attempts. Try again in a few minutes.";
  }
  return `Couldn’t log in: ${error.message}`;
}

export function LoginPage() {
  const [password, setPassword] = useState("");
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const session = useQuery({ queryKey: SESSION_QUERY_KEY, queryFn: hasSession, staleTime: Infinity });
  const signIn = useMutation({
    mutationFn: login,
    onSuccess: () => {
      queryClient.setQueryData(SESSION_QUERY_KEY, true);
      navigate("/", { replace: true });
    },
  });

  if (session.data) return <Navigate to="/" replace />;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (password) signIn.mutate(password);
  }

  return (
    <main className={styles.page}>
      <form className={styles.card} onSubmit={onSubmit}>
        <h1 className={styles.heading}>
          <Logo />
        </h1>
        <label htmlFor="password" className={styles.label}>
          Password
        </label>
        <input
          id="password"
          className={styles.input}
          type="password"
          autoComplete="current-password"
          autoFocus
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          aria-invalid={signIn.isError}
          aria-describedby={signIn.isError ? "login-error" : undefined}
        />
        {signIn.isError && (
          <p id="login-error" role="alert" className={styles.error}>
            {loginError(signIn.error)}
          </p>
        )}
        <button type="submit" className={styles.submit} disabled={!password || signIn.isPending}>
          {signIn.isPending ? "Logging in…" : "Log in"}
        </button>
      </form>
    </main>
  );
}
