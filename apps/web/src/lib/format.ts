import type { MatchStatus, Role } from "../api/types";

export const STATUS_LABELS: Record<MatchStatus, string> = {
  new: "New",
  saved: "Saved",
  applied: "Applied",
  dismissed: "Dismissed",
};

/** "21–29", "18+", "25", or null when the role gives no ages. */
export function formatAges({ age_min, age_max }: Pick<Role, "age_min" | "age_max">) {
  if (age_min === null && age_max === null) return null;
  if (age_max === null) return `${age_min}+`;
  if (age_min === null) return `up to ${age_max}`;
  if (age_min === age_max) return String(age_min);
  return `${age_min}–${age_max}`;
}

/** "Brooklyn, NY", "Brooklyn, NY +2 more", or null. */
export function formatLocations(locations: string[]) {
  const [first, ...rest] = locations;
  if (!first) return null;
  return rest.length ? `${first} +${rest.length} more` : first;
}

export interface DeadlineDisplay {
  text: string;
  full: string | null; // date and time, for a tooltip
  closed: boolean;
}

export function formatDeadline(iso: string | null, now: Date = new Date()): DeadlineDisplay {
  if (!iso) return { text: "Not listed", full: null, closed: false };
  const deadline = new Date(iso);
  const sameYear = deadline.getFullYear() === now.getFullYear();
  const day = deadline.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    ...(sameYear ? {} : { year: "numeric" }),
  });
  const full = deadline.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
  const closed = deadline.getTime() < now.getTime();
  return { text: closed ? `Closed ${day}` : day, full, closed };
}

const UNION_LABELS: Record<string, string> = {
  union: "Union",
  nonunion: "Non-union",
  union_and_nonunion: "Union and non-union",
};

export function formatUnion(value: string | null): string | null {
  return value ? (UNION_LABELS[value] ?? value) : null;
}

/** ["female", "trans female"] -> "Female, trans female"; [] means open to any gender. */
export function formatGenders(genders: string[]): string {
  if (genders.length === 0) return "Any gender";
  const text = genders.join(", ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
