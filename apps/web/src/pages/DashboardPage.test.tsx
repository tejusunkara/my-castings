import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";

import { App } from "../App";
import { createQueryClient } from "../queryClient";
import { makeMatch, SUMMARY } from "../test/fixtures";

const INITIAL_MATCHES = [
  makeMatch({ id: 1 }),
  makeMatch({
    id: 2,
    status: "saved",
    role: { role_name: "Background Bargoer" },
    casting_call: { source_key: "actors_access", title: "What Happened Last Night" },
  }),
];

interface Call {
  method: string;
  path: string;
  params: URLSearchParams;
  body: unknown;
}

let calls: Call[];
let MATCHES: typeof INITIAL_MATCHES;
let loggedIn: boolean;

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  calls = [];
  loggedIn = true;
  MATCHES = INITIAL_MATCHES.map((m) => ({ ...m }));
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      const url = new URL(input, "http://localhost");
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ method, path: url.pathname, params: url.searchParams, body });

      if (url.pathname === "/api/auth/session") {
        return loggedIn ? new Response(null, { status: 204 }) : json({ detail: "not logged in" }, 401);
      }
      if (url.pathname === "/api/auth/login") {
        if (body.password !== "right") return json({ detail: "wrong password" }, 401);
        loggedIn = true;
        return new Response(null, { status: 204 });
      }
      if (url.pathname === "/api/matches/summary") return json(SUMMARY);
      if (url.pathname === "/api/matches" && method === "GET") return json(MATCHES);
      const patch = url.pathname.match(/^\/api\/matches\/(\d+)$/);
      if (patch && method === "PATCH") {
        const match = MATCHES.find((m) => m.id === Number(patch[1]))!;
        Object.assign(match, body);
        return json(match);
      }
      return json({ detail: "not found" }, 404);
    }),
  );
});

afterEach(() => vi.unstubAllGlobals());

// The router's current location, recorded after each render for assertions.
const probe: { location?: ReturnType<typeof useLocation> } = {};
function LocationProbe() {
  const current = useLocation();
  useEffect(() => {
    probe.location = current;
  }, [current]);
  return null;
}

function renderApp(path = "/") {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <App />
        <Routes>
          <Route path="*" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const listCalls = () => calls.filter((c) => c.path === "/api/matches" && c.method === "GET");
const lastList = () => listCalls().at(-1)!.params;

describe("DashboardPage", () => {
  it("shows matches, status counts and the shown total", async () => {
    renderApp();
    expect(await screen.findByRole("heading", { name: /Bright Side Soda/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /What Happened Last Night/ })).toBeInTheDocument();
    // new + saved + applied are shown by default: 2 + 1 + 0
    expect(screen.getByText("3 roles")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dismissed (3)" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(lastList().getAll("status")).toEqual(["new", "saved", "applied"]);
    expect(lastList().get("sort")).toBe("deadline");
  });

  it("status tiles toggle which statuses are listed", async () => {
    renderApp();
    await screen.findByText("3 roles");
    await userEvent.click(screen.getByRole("button", { name: "Dismissed (3)" }));
    await waitFor(() =>
      expect(lastList().getAll("status")).toEqual(["new", "saved", "applied", "dismissed"]),
    );
    expect(probe.location?.search).toBe("?status=new%2Csaved%2Capplied%2Cdismissed");
  });

  it("filters by source, project type and search, and sorts", async () => {
    renderApp();
    await screen.findByText("3 roles");

    await userEvent.click(screen.getByRole("checkbox", { name: "Backstage" }));
    await waitFor(() => expect(lastList().getAll("source")).toEqual(["actors_access", "casting_networks"]));

    await userEvent.selectOptions(screen.getByLabelText("Project type"), "Web Series");
    await waitFor(() => expect(lastList().get("project_type")).toBe("Web Series"));

    await userEvent.type(screen.getByLabelText("Search"), "queens");
    await waitFor(() => expect(lastList().get("q")).toBe("queens"));
    // The summary counts follow the same filters.
    const summaryCall = calls.filter((c) => c.path === "/api/matches/summary").at(-1)!;
    expect(summaryCall.params.get("q")).toBe("queens");

    await userEvent.selectOptions(screen.getByLabelText("Sort"), "posted");
    await waitFor(() => expect(lastList().get("sort")).toBe("posted"));
  });

  it("asks for a source instead of querying when none is checked", async () => {
    renderApp("/?sources=backstage");
    await userEvent.click(await screen.findByRole("checkbox", { name: "Backstage" }));
    expect(await screen.findByText("Pick at least one source to see roles.")).toBeInTheDocument();
    expect(listCalls().every((c) => c.params.getAll("source").length > 0)).toBe(true);
  });

  it("changes a role's status", async () => {
    renderApp();
    const card = (await screen.findByRole("heading", { name: /Bright Side Soda/ })).closest("article")!;
    await userEvent.click(within(card).getByRole("radio", { name: "Applied" }));
    const patch = calls.find((c) => c.method === "PATCH")!;
    expect(patch.path).toBe("/api/matches/1");
    expect(patch.body).toEqual({ status: "applied" });
    expect(within(card).getByRole("radio", { name: "Applied" })).toHaveAttribute("aria-checked", "true");
  });
});

describe("login", () => {
  it("redirects to login without a session, then back after logging in", async () => {
    loggedIn = false;
    renderApp();
    const password = await screen.findByLabelText("Password");
    await userEvent.type(password, "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That password isn’t right.");

    await userEvent.clear(password);
    await userEvent.type(password, "right");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("heading", { name: /Bright Side Soda/ })).toBeInTheDocument();
    expect(probe.location?.pathname).toBe("/");
  });
});
