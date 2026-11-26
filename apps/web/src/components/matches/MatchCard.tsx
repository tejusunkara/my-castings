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
        {role.apply_url ? (
          // The link carries a token tied to the artist's account: no referrer, new tab.
          <a
            href={role.apply_url}
            target="_blank"
            rel="noopener noreferrer"
            title={`Open on ${source} (link is personal to your account)`}
          >
            {call.title}
            <span aria-hidden="true" className={styles.external}>
              ↗
            </span>
          </a>
        ) : (
          call.title
        )}
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
        <dd title={deadline.full ?? undefined} className={deadline.closed ? styles.closed : undefined}>
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
