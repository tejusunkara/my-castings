import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MediaAsset } from "../api/types";
import { installFakeStorage, installMockApi } from "../test/mockApi";
import { renderApp } from "../test/renderApp";

afterEach(() => vi.unstubAllGlobals());

function asset(fields: Partial<MediaAsset> & { id: number }): MediaAsset {
  return {
    asset_type: "headshot",
    label: null,
    is_current: true,
    upload_status: "completed",
    content_type: "image/jpeg",
    file_size_bytes: 2_400_000,
    original_filename: "ana.jpg",
    external_url: null,
    created_at: "2026-11-20T12:00:00Z",
    completed_at: "2026-11-20T12:00:00Z",
    view_url: "http://storage.test/ana.jpg?sig",
    ...fields,
  };
}

const section = async (title: string) =>
  (await screen.findByRole("heading", { name: title, level: 2 })).closest("section")!;

describe("MediaPage", () => {
  it("shows current items and keeps older ones in the archive", async () => {
    installMockApi({
      media: [
        asset({ id: 1, label: "Theatrical" }),
        asset({ id: 2, label: "2024 headshot", is_current: false, original_filename: "old.jpg" }),
        asset({
          id: 3,
          asset_type: "social_link",
          external_url: "https://www.instagram.com/ana",
          content_type: null,
          view_url: null,
        }),
      ],
    });
    renderApp("/media");
    const headshots = await section("Headshots");
    expect(within(headshots).getByRole("img", { name: "Theatrical" })).toHaveAttribute(
      "src",
      "http://storage.test/ana.jpg?sig",
    );
    expect(within(headshots).getByText("Archive (1)")).toBeInTheDocument();
    expect(within(headshots).getByText("ana.jpg · 2.3 MB · Nov 20, 2026")).toBeInTheDocument();

    const social = await section("Social links");
    expect(within(social).getByRole("link", { name: "Instagram ↗" })).toHaveAttribute(
      "href",
      "https://www.instagram.com/ana",
    );
    expect(within(await section("Acting resume")).getByText("Nothing current yet.")).toBeVisible();
  });

  it("uploads a file straight to storage, then confirms it", async () => {
    const api = installMockApi();
    const sent = installFakeStorage();
    renderApp("/media");
    const headshots = await section("Headshots");
    const file = new File(["jpegdata"], "new.jpg", { type: "image/jpeg" });
    await userEvent.upload(within(headshots).getByLabelText(/Upload files/), file);

    await waitFor(() => expect(api.calls.some((c) => c.path.endsWith("/complete"))).toBe(true));
    expect(api.calls.find((c) => c.path === "/media/uploads")?.body).toEqual({
      asset_type: "headshot",
      filename: "new.jpg",
      content_type: "image/jpeg",
      size_bytes: 8,
    });
    expect(sent).toHaveLength(1);
    expect(sent[0]!.url).toBe("http://storage.test/my-castings-media");
    expect(sent[0]!.fields).toMatchObject({ key: "media/headshot/abc", policy: "p" });
    expect(sent[0]!.file?.name).toBe("new.jpg");
    expect(await within(headshots).findByText("new.jpg")).toBeInTheDocument();
  });

  it("rejects a wrong file type before uploading anything", async () => {
    const api = installMockApi();
    installFakeStorage();
    renderApp("/media");
    const resume = await section("Acting resume");
    const photo = new File(["x"], "me.jpg", { type: "image/jpeg" });
    await userEvent.upload(within(resume).getByLabelText(/Upload a file/), photo, {
      applyAccept: false,
    });
    expect(await within(resume).findByRole("alert")).toHaveTextContent(
      "me.jpg isn’t a supported file here. PDF, up to 10 MB.",
    );
    expect(api.calls.some((c) => c.path === "/media/uploads")).toBe(false);
  });

  it("cleans up when storage refuses the upload", async () => {
    const api = installMockApi();
    installFakeStorage(400);
    renderApp("/media");
    const reels = await section("Acting reels");
    const video = new File(["v"], "reel.mp4", { type: "video/mp4" });
    await userEvent.upload(within(reels).getByLabelText(/Upload a file/), video);
    expect(await within(reels).findByRole("alert")).toHaveTextContent(
      "Upload failed: the file is larger than this type allows",
    );
    await waitFor(() => expect(api.calls.some((c) => c.method === "DELETE")).toBe(true));
    expect(api.state.media).toEqual([]);
  });

  it("adds a link, archives it and deletes it", async () => {
    const api = installMockApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderApp("/media");
    const reels = await section("Acting reels");
    await userEvent.type(
      within(reels).getByLabelText("Link for Acting reels"),
      "https://vimeo.com/1",
    );
    await userEvent.type(within(reels).getByLabelText("Label (optional)"), "2026 reel");
    await userEvent.click(within(reels).getByRole("button", { name: "Add link" }));
    expect(await within(reels).findByText("2026 reel")).toBeInTheDocument();
    expect(api.calls.find((c) => c.path === "/media/links")?.body).toEqual({
      asset_type: "acting_reel",
      url: "https://vimeo.com/1",
      label: "2026 reel",
    });

    await userEvent.click(within(reels).getByRole("button", { name: "Move to archive" }));
    expect(await within(reels).findByText("Archive (1)")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({ is_current: false });

    await userEvent.click(within(reels).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(within(reels).queryByText("2026 reel")).not.toBeInTheDocument());
  });
});
