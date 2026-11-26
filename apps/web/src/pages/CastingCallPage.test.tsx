import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeCastingCall } from "../test/fixtures";
import { installMockApi } from "../test/mockApi";
import { renderApp } from "../test/renderApp";

let api: ReturnType<typeof installMockApi>;

beforeEach(() => {
  api = installMockApi({ castingCalls: [makeCastingCall()] });
});

afterEach(() => vi.unstubAllGlobals());

const roleSection = async (name: string) =>
  (await screen.findByRole("heading", { name, level: 3 })).closest("section")!;

describe("CastingCallPage", () => {
  it("shows the posting and every role", async () => {
    renderApp("/casting-calls/100");
    expect(
      await screen.findByRole("heading", { name: "Bright Side Soda", level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByText("A fizzy spot for a new soda.")).toBeInTheDocument();
    expect(screen.getByText("Non-union")).toBeInTheDocument();
    expect(screen.getByText("New York, NY; Brooklyn, NY")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "2 roles" })).toBeInTheDocument();

    const lead = await roleSection("Lead Girl");
    expect(within(lead).getByText("Lead · Female · ages 21–29")).toBeInTheDocument();
    expect(within(lead).getByRole("link", { name: /Open on Backstage/ })).toHaveAttribute(
      "rel",
      expect.stringContaining("noreferrer"),
    );

    const dad = await roleSection("Dad");
    expect(within(dad).getByText(/Doesn’t match your profile/)).toBeInTheDocument();
    expect(within(dad).queryByRole("radiogroup")).not.toBeInTheDocument();
  });

  it("changes a matched role's status and saves a note", async () => {
    renderApp("/casting-calls/100");
    const lead = await roleSection("Lead Girl");
    await userEvent.click(within(lead).getByRole("radio", { name: "Saved" }));
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({ status: "saved" });

    await userEvent.type(within(lead).getByLabelText("Note for Lead Girl"), " self-tape Fri ");
    await userEvent.click(within(lead).getByRole("button", { name: "Save note" }));
    expect(api.calls.filter((c) => c.method === "PATCH").at(-1)?.body).toEqual({
      user_note: "self-tape Fri",
    });
  });

  it("explains a missing casting call", async () => {
    renderApp("/casting-calls/999");
    expect(await screen.findByRole("alert")).toHaveTextContent("doesn’t exist");
  });
});
