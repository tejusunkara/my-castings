import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeMatch } from "../test/fixtures";
import { installMockApi } from "../test/mockApi";
import { probe, renderApp } from "../test/renderApp";

let api: ReturnType<typeof installMockApi>;

beforeEach(() => {
  api = installMockApi({
    matches: [
      makeMatch({ id: 1 }),
      makeMatch({
        id: 2,
        status: "saved",
        role: { role_name: "Background Bargoer" },
        casting_call: { source_key: "actors_access", title: "What Happened Last Night" },
      }),
    ],
  });
});

afterEach(() => vi.unstubAllGlobals());

const listCalls = () => api.calls.filter((c) => c.path === "/matches" && c.method === "GET");
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
    await waitFor(() =>
      expect(lastList().getAll("source")).toEqual(["actors_access", "casting_networks"]),
    );

    await userEvent.selectOptions(screen.getByLabelText("Project type"), "Web Series");
    await waitFor(() => expect(lastList().get("project_type")).toBe("Web Series"));

    await userEvent.type(screen.getByLabelText("Search"), "queens");
    await waitFor(() => expect(lastList().get("q")).toBe("queens"));
    // The summary counts follow the same filters.
    const summaryCall = api.calls.filter((c) => c.path === "/matches/summary").at(-1)!;
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
    const card = (await screen.findByRole("heading", { name: /Bright Side Soda/ })).closest(
      "article",
    )!;
    await userEvent.click(within(card).getByRole("radio", { name: "Applied" }));
    const patch = api.calls.find((c) => c.method === "PATCH")!;
    expect(patch.path).toBe("/matches/1");
    expect(patch.body).toEqual({ status: "applied" });
    expect(within(card).getByRole("radio", { name: "Applied" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("opens the detail page from a card title", async () => {
    renderApp();
    await userEvent.click(await screen.findByRole("link", { name: "Bright Side Soda" }));
    expect(probe.location?.pathname).toBe("/casting-calls/100");
  });
});

describe("login", () => {
  it("redirects to login without a session, then back after logging in", async () => {
    api.state.loggedIn = false;
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

  it("sends an expired session back to login", async () => {
    renderApp();
    await screen.findByText("3 roles");
    api.state.loggedIn = false;
    await userEvent.click(screen.getByRole("link", { name: "Profile" }));
    expect(await screen.findByLabelText("Password")).toBeInTheDocument();
  });
});
