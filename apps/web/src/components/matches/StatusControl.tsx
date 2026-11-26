import { MATCH_STATUSES, type MatchStatus } from "../../api/types";
import { STATUS_LABELS } from "../../lib/format";
import styles from "./StatusControl.module.css";

interface Props {
  value: MatchStatus;
  onChange: (status: MatchStatus) => void;
  disabled?: boolean;
  label: string;
}

/** Segmented control for a role's submission status. */
export function StatusControl({ value, onChange, disabled, label }: Props) {
  return (
    <div className={styles.group} role="radiogroup" aria-label={label}>
      {MATCH_STATUSES.map((status) => (
        <button
          key={status}
          type="button"
          role="radio"
          aria-checked={value === status}
          className={styles.option}
          data-status={status}
          disabled={disabled}
          onClick={() => value !== status && onChange(status)}
        >
          {STATUS_LABELS[status]}
        </button>
      ))}
    </div>
  );
}
