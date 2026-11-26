import { MATCH_STATUSES, type MatchStatus } from "../../api/types";
import { STATUS_LABELS } from "../../lib/format";
import styles from "./StatusTiles.module.css";

interface Props {
  counts: Record<MatchStatus, number> | undefined;
  selected: MatchStatus[];
  onToggle: (status: MatchStatus) => void;
}

/** One tile per status with its count; clicking a tile shows or hides that status. */
export function StatusTiles({ counts, selected, onToggle }: Props) {
  return (
    <div className={styles.tiles} role="group" aria-label="Show statuses">
      {MATCH_STATUSES.map((status) => (
        <button
          key={status}
          type="button"
          className={styles.tile}
          aria-pressed={selected.includes(status)}
          aria-label={counts ? `${STATUS_LABELS[status]} (${counts[status]})` : STATUS_LABELS[status]}
          onClick={() => onToggle(status)}
        >
          <span className={styles.count}>{counts ? counts[status] : "–"}</span>
          <span className={styles.label}>{STATUS_LABELS[status]}</span>
        </button>
      ))}
    </div>
  );
}
