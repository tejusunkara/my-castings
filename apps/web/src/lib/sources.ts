/** Per-source accent colors, matching the source pills in the header and filters. */
const SOURCE_COLORS: Record<string, string> = {
  casting_networks: "var(--source-casting-networks)",
  backstage: "var(--source-backstage)",
  actors_access: "var(--source-actors-access)",
};

export function sourceColor(key: string): string {
  return SOURCE_COLORS[key] ?? "var(--source-other)";
}

const SOURCE_NAMES: Record<string, string> = {
  casting_networks: "Casting Networks",
  backstage: "Backstage",
  actors_access: "Actors Access",
};

export function sourceName(key: string): string {
  return SOURCE_NAMES[key] ?? key.replace(/_/g, " ");
}
