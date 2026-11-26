import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeRawEmail } from "../test/fixtures";
import { installMockApi } from "../test/mockApi";
import { renderApp } from "../test/renderApp";

afterEach(() => vi.unstubAllGlobals());

describe("AdminPage", () => {
  it("lists emails needing attention and reprocesses one", async () => {
    const email = makeRawEmail();
    const api = installMockApi({
      rawEmails: [email],
      reprocess: {
        raw_email: { ...email, parse_status: "success", parse_error: null },
        created_roles: 5,
        updated_roles: 0,
        deleted_roles: 0,
        kept_role_ids: [],
        new_matches: 3,
      },
    });
    renderApp("/admin");

    expect(await screen.findByText("Fwd: Projects match your profile")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("no adapter for sender 'redacted@gmail.com'")).toBeInTheDocument();
    expect(
      api.calls.find((c) => c.path === "/admin/raw-emails")?.params.get("needs_attention"),
    ).toBe("true");

    await userEvent.click(screen.getByRole("button", { name: "Reprocess" }));
    expect(
      await screen.findByText(/5 new, 0 updated, 0 removed roles; 3 new matches/),
    ).toBeInTheDocument();
    expect(api.calls.some((c) => c.path === "/admin/raw-emails/7/reprocess")).toBe(true);
  });

  it("switches to all emails", async () => {
    const api = installMockApi({ rawEmails: [] });
    renderApp("/admin");
    expect(await screen.findByText(/Nothing needs attention/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "All emails" }));
    expect(await screen.findByText("No emails yet.")).toBeInTheDocument();
    const last = api.calls.filter((c) => c.path === "/admin/raw-emails").at(-1)!;
    expect(last.params.has("needs_attention")).toBe(false);
  });
});
