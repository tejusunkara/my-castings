import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeProfile } from "../test/fixtures";
import { installMockApi } from "../test/mockApi";
import { renderApp } from "../test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const lastPut = (api: ReturnType<typeof installMockApi>) =>
  api.calls.filter((c) => c.method === "PUT").at(-1)?.body;

describe("ProfilePage", () => {
  it("edits and saves the profile, keeping labels outside the preset list", async () => {
    const api = installMockApi({ profile: makeProfile() });
    renderApp("/profile");

    const from = await screen.findByLabelText("Playing age from");
    expect(from).toHaveValue(16);
    expect(screen.getByRole("checkbox", { name: "any gender" })).toBeChecked();

    await userEvent.clear(from);
    await userEvent.type(from, "18");
    await userEvent.click(screen.getByRole("checkbox", { name: "non-binary" }));
    await userEvent.type(screen.getByLabelText("Another gender label"), "Androgynous{Enter}");
    await userEvent.click(screen.getByRole("button", { name: "Save profile" }));

    expect(await screen.findByText("Saved. Matches are updated.")).toBeInTheDocument();
    expect(lastPut(api)).toMatchObject({
      playing_age_min: 18,
      playing_age_max: 30,
      genders: ["female", "any gender", "femme presenting", "non-binary", "androgynous"],
      location_state: "NY",
      willing_to_travel: true,
    });
  });

  it("creates a profile when there is none", async () => {
    const api = installMockApi({ profile: null });
    renderApp("/profile");
    await userEvent.type(await screen.findByLabelText("City"), "Queens");
    await userEvent.type(screen.getByLabelText("State"), "ny");
    await userEvent.click(screen.getByRole("button", { name: "Create profile" }));
    expect(await screen.findByText("Saved. Matches are updated.")).toBeInTheDocument();
    expect(lastPut(api)).toMatchObject({ location_city: "Queens", location_state: "NY" });
  });

  it("blocks a half-set or inverted age range", async () => {
    const api = installMockApi({ profile: makeProfile() });
    renderApp("/profile");
    const to = await screen.findByLabelText("Playing age to");
    await userEvent.clear(to);
    expect(screen.getByText("Set both ages, or neither.")).toBeInTheDocument();
    await userEvent.type(to, "10");
    expect(screen.getByText("The lower age can’t be above the upper one.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save profile" }));
    expect(lastPut(api)).toBeUndefined();
  });
});
