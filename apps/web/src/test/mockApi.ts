/**
 * An in-memory stand-in for the FastAPI backend, installed as the global fetch. Tests
 * seed `api.state`, render the app, then assert on the UI and on `api.calls`.
 */
import { vi } from "vitest";

import type { CastingCall, Match, Profile, RawEmail, ReprocessResult } from "../api/types";
import { SUMMARY } from "./fixtures";

export interface Call {
  method: string;
  path: string;
  params: URLSearchParams;
  body: unknown;
}

export interface ApiState {
  loggedIn: boolean;
  password: string;
  matches: Match[];
  castingCalls: CastingCall[];
  profile: Profile | null;
  rawEmails: RawEmail[];
  reprocess?: ReprocessResult;
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const empty = (status: number) => new Response(null, { status });

export function installMockApi(state: Partial<ApiState> = {}) {
  const api = {
    calls: [] as Call[],
    state: {
      loggedIn: true,
      password: "right",
      matches: [],
      castingCalls: [],
      profile: null,
      rawEmails: [],
      ...state,
    } as ApiState,
  };

  const route = (method: string, path: string, body: Record<string, unknown>): Response => {
    const s = api.state;
    if (path === "/auth/session") return s.loggedIn ? empty(204) : json({ detail: "x" }, 401);
    if (path === "/auth/login") {
      if (body.password !== s.password) return json({ detail: "wrong password" }, 401);
      s.loggedIn = true;
      return empty(204);
    }
    if (!s.loggedIn) return json({ detail: "not logged in" }, 401);

    if (path === "/matches/summary") return json(SUMMARY);
    if (path === "/matches") return json(s.matches);
    let m = path.match(/^\/matches\/(\d+)$/);
    if (m && method === "PATCH") {
      const id = Number(m[1]);
      const match = s.matches.find((x) => x.id === id);
      if (match) Object.assign(match, body);
      for (const call of s.castingCalls) {
        for (const role of call.roles) {
          if (role.saved_match?.id === id) Object.assign(role.saved_match, body);
        }
      }
      return json(match ?? {});
    }
    m = path.match(/^\/casting-calls\/(\d+)$/);
    if (m) {
      const call = s.castingCalls.find((c) => c.id === Number(m![1]));
      return call ? json(call) : json({ detail: "casting call not found" }, 404);
    }
    if (path === "/profile" && method === "GET") {
      return s.profile ? json(s.profile) : json({ detail: "no profile yet" }, 404);
    }
    if (path === "/profile" && method === "PUT") {
      s.profile = { id: 1, updated_at: new Date().toISOString(), ...(body as object) } as Profile;
      return json(s.profile);
    }
    if (path === "/admin/raw-emails") return json(s.rawEmails);
    m = path.match(/^\/admin\/raw-emails\/(\d+)\/reprocess$/);
    if (m && s.reprocess) return json(s.reprocess);
    return json({ detail: "not found" }, 404);
  };

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      const url = new URL(input, "http://localhost");
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      const path = url.pathname.replace(/^\/api/, "");
      api.calls.push({ method, path, params: url.searchParams, body });
      return route(method, path, body);
    }),
  );
  return api;
}
