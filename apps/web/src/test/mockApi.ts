/**
 * An in-memory stand-in for the FastAPI backend, installed as the global fetch. Tests
 * seed `api.state`, render the app, then assert on the UI and on `api.calls`.
 */
import { vi } from "vitest";

import type {
  CastingCall,
  Match,
  MediaAsset,
  Profile,
  RawEmail,
  ReprocessResult,
} from "../api/types";
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
  media: MediaAsset[];
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
      media: [],
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
    if (path === "/media" && method === "GET") return json(s.media);
    if (path === "/media/uploads") {
      const asset = mediaAsset(s, {
        asset_type: body.asset_type as MediaAsset["asset_type"],
        original_filename: body.filename as string,
        content_type: body.content_type as string,
        file_size_bytes: body.size_bytes as number,
        upload_status: "pending",
      });
      return json(
        {
          asset,
          upload: {
            url: "http://storage.test/my-castings-media",
            fields: { key: `media/${asset.asset_type}/abc`, policy: "p", "x-amz-signature": "s" },
          },
        },
        201,
      );
    }
    if (path === "/media/links") {
      const asset = mediaAsset(s, {
        asset_type: body.asset_type as MediaAsset["asset_type"],
        external_url: body.url as string,
        label: (body.label as string) ?? null,
      });
      return json(asset, 201);
    }
    m = path.match(/^\/media\/(\d+)(\/complete)?$/);
    if (m) {
      const asset = s.media.find((a) => a.id === Number(m![1]));
      if (!asset) return json({ detail: "media not found" }, 404);
      if (m[2]) {
        Object.assign(asset, { upload_status: "completed", view_url: "http://storage.test/view" });
        return json(asset);
      }
      if (method === "PATCH") return json(Object.assign(asset, body));
      if (method === "DELETE") {
        s.media = s.media.filter((a) => a !== asset);
        return empty(204);
      }
    }
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

let nextMediaId = 1000;

function mediaAsset(state: ApiState, fields: Partial<MediaAsset>): MediaAsset {
  const asset: MediaAsset = {
    id: nextMediaId++,
    asset_type: "headshot",
    label: null,
    is_current: true,
    upload_status: "completed",
    content_type: null,
    file_size_bytes: null,
    original_filename: null,
    external_url: null,
    created_at: "2026-11-26T12:00:00Z",
    completed_at: "2026-11-26T12:00:00Z",
    view_url: null,
    ...fields,
  };
  state.media.push(asset);
  return asset;
}

/** Stands in for the browser's direct upload to storage (XMLHttpRequest). */
export function installFakeStorage(status = 204) {
  const sent: { url: string; fields: Record<string, string>; file: File | null }[] = [];
  class FakeXHR {
    status = 0;
    responseText = "";
    upload: { onprogress: ((e: ProgressEvent) => void) | null } = { onprogress: null };
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    private url = "";
    open(_method: string, url: string) {
      this.url = url;
    }
    send(body: FormData) {
      const fields: Record<string, string> = {};
      let file: File | null = null;
      body.forEach((value, key) => {
        if (value instanceof File) file = value;
        else fields[key] = value;
      });
      sent.push({ url: this.url, fields, file });
      setTimeout(() => {
        this.upload.onprogress?.({ lengthComputable: true, loaded: 1, total: 2 } as ProgressEvent);
        this.status = status;
        this.responseText =
          status === 204
            ? ""
            : "<Error><Code>EntityTooLarge</Code><Message>too big</Message></Error>";
        this.onload?.();
      }, 0);
    }
  }
  vi.stubGlobal("XMLHttpRequest", FakeXHR);
  return sent;
}
