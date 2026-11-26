import type { Source } from "../../api/types";
import { toggle } from "../../lib/filters";
import { sourceColor } from "../../lib/sources";
import styles from "./FiltersPanel.module.css";

interface Props {
  search: string;
  onSearchChange: (value: string) => void;
  sources: Source[];
  selectedSources: string[] | null; // null = all
  onSourcesChange: (keys: string[] | null) => void;
  projectTypes: string[];
  projectType: string;
  onProjectTypeChange: (value: string) => void;
}

export function FiltersPanel(props: Props) {
  const { sources, selectedSources } = props;
  const isChecked = (key: string) => selectedSources === null || selectedSources.includes(key);

  function onSourceToggle(key: string) {
    const current = selectedSources ?? sources.map((s) => s.key);
    const next = toggle(current, key);
    // Every source checked again is the same as "all", including sources added later.
    props.onSourcesChange(sources.every((s) => next.includes(s.key)) ? null : next);
  }

  // Keep a selected type in the list even if no current match has it.
  const typeOptions =
    props.projectType && !props.projectTypes.includes(props.projectType)
      ? [props.projectType, ...props.projectTypes]
      : props.projectTypes;

  return (
    <section className={styles.panel} aria-labelledby="filters-heading">
      <h2 id="filters-heading" className={styles.heading}>
        Filters
      </h2>

      <label className="visually-hidden" htmlFor="filter-search">
        Search
      </label>
      <input
        id="filter-search"
        className={styles.search}
        type="search"
        placeholder="Search roles, titles, cities…"
        value={props.search}
        onChange={(e) => props.onSearchChange(e.target.value)}
        autoComplete="off"
      />

      <fieldset className={styles.group}>
        <legend className={styles.label}>Sources</legend>
        {sources.map((source) => (
          <label key={source.key} className={styles.check}>
            <input
              type="checkbox"
              checked={isChecked(source.key)}
              onChange={() => onSourceToggle(source.key)}
            />
            <span className={styles.dot} style={{ background: sourceColor(source.key) }} />
            {source.display_name}
          </label>
        ))}
      </fieldset>

      <div className={styles.group}>
        <label className={styles.label} htmlFor="filter-type">
          Project type
        </label>
        <select
          id="filter-type"
          className={styles.select}
          value={props.projectType}
          onChange={(e) => props.onProjectTypeChange(e.target.value)}
        >
          <option value="">All</option>
          {typeOptions.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </div>
    </section>
  );
}
