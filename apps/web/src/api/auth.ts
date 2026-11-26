import { ApiError, request } from "./client";

export const SESSION_QUERY_KEY = ["session"] as const;

export const login = (password: string) =>
  request<void>("POST", "/auth/login", { body: { password } });

export const logout = () => request<void>("POST", "/auth/logout");

/** true when the session cookie is valid, false when the API says 401. */
export async function hasSession(): Promise<boolean> {
  try {
    await request<void>("GET", "/auth/session");
    return true;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return false;
    throw error;
  }
}
