import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { makeMatch } from "../../test/fixtures";
import { MatchCard } from "./MatchCard";

describe("MatchCard", () => {
  it("shows the role's details", () => {
    render(<MatchCard match={makeMatch({ id: 1 })} onStatusChange={() => {}} />);
    expect(screen.getByRole("heading", { name: /Bright Side Soda/ })).toBeInTheDocument();
    expect(screen.getByText("Backstage")).toBeInTheDocument();
    expect(screen.getByText("Commercial")).toBeInTheDocument();
    expect(screen.getByText(/Lead Girl/)).toHaveTextContent("Lead Girl, 21–29");
    expect(screen.getByText("New York, NY")).toBeInTheDocument();
    expect(screen.getByText("$850 for 9 hours of work")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "New" })).toHaveAttribute("aria-checked", "true");
  });

  it("opens the personal apply link without a referrer", () => {
    render(<MatchCard match={makeMatch({ id: 1 })} onStatusChange={() => {}} />);
    const link = screen.getByRole("link", { name: /Bright Side Soda/ });
    expect(link).toHaveAttribute("href", "https://example.com/apply?token=secret");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noreferrer");
  });

  it("says when pay, location and deadline aren't given", () => {
    const match = makeMatch({
      id: 2,
      role: { pay: null },
      casting_call: { seeking_locations: [], submission_deadline: null },
    });
    render(<MatchCard match={match} onStatusChange={() => {}} />);
    expect(screen.getAllByText("Not listed")).toHaveLength(3);
  });

  it("reports a status change, but not a click on the current status", async () => {
    const onStatusChange = vi.fn();
    render(<MatchCard match={makeMatch({ id: 1 })} onStatusChange={onStatusChange} />);
    await userEvent.click(screen.getByRole("radio", { name: "New" }));
    await userEvent.click(screen.getByRole("radio", { name: "Applied" }));
    expect(onStatusChange).toHaveBeenCalledExactlyOnceWith("applied");
  });
});
