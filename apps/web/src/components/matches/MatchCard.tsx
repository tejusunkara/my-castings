import { Link } from "react-router";

import type { Match, MatchStatus } from "../../api/types";
import { formatAges, formatDeadline, formatLocations } from "../../lib/format";
import { sourceColor, sourceName } from "../../lib/sources";
import styles from "./MatchCard.module.css";
import { StatusControl } from "./StatusControl";

interface Props {
  match: Match;
  onStatusChange: (status: MatchStatus) => void;
  updating?: boolean;
}

export function MatchCard({ match, onStatusChange, updating }: Props) {
  const { role, casting_call: call } = match;
  const color = sourceColor(call.source_key);
  const source = sourceName(call.source_key);
  const ages = formatAges(role);
  const deadline = formatDeadline(call.submission_deadline);
  const location = formatLocations(call.seeking_locations);

  return (
    <article
      className={styles.card}
      style={{ borderTopColor: color }}
      data-status={match.status}
      aria-labelledby={`match-${match.id}-title`}
    >
      <div className={styles.top}>
        <span className={styles.badge} style={{ background: color }}>
          {source}
        </span>
        {call.project_type && <span className={styles.type}>{call.project_type}</span>}
      </div>

      <h2 className={styles.title} id={`match-${match.id}-title`}>
        <Link to={`/casting-calls/${call.id}`}>{call.title}</Link>
        {role.apply_url && <ApplyLink href={role.apply_url} source={source} compact />}
      </h2>
      <p className={styles.role}>
        {role.role_name}
        {ages && <span className={styles.ages}>, {ages}</span>}
      </p>

      <dl className={styles.facts}>
        <dt>Location</dt>
        <dd title={call.seeking_locations.join("; ") || undefined}>{location ?? "Not listed"}</dd>
        <dt>Pay</dt>
        <dd className={styles.clamp} title={role.pay ?? undefined}>
          {role.pay ?? "Not listed"}
        </dd>
        <dt>Deadline</dt>
        <dd
          title={deadline.full ?? undefined}
          className={deadline.closed ? styles.closed : undefined}
        >
          {deadline.text}
        </dd>
      </dl>

      <StatusControl
        value={match.status}
        onChange={onStatusChange}
        disabled={updating}
        label={`Status for ${role.role_name} in ${call.title}`}
      />
    </article>
  );
}

/** Link to the role on the source site. The URL carries a token tied to the artist's
 * account, so it opens in a new tab and sends no referrer. */
export function ApplyLink({
  href,
  source,
  compact = false,
}: {
  href: string;
  source: string;
  compact?: boolean;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={compact ? styles.external : styles.applyButton}
      aria-label={compact ? `Open on ${source}` : undefined}
      title={`Open on ${source} (the link is personal to your account)`}
    >
      {compact ? "↗" : `Open on ${source} ↗`}
    </a>
  );
}
