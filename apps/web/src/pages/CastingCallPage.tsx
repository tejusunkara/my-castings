import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { ApiError, isUnauthorized } from "../api/client";
import { getCastingCall } from "../api/castingCalls";
import type { RoleDetail } from "../api/types";
import { ApplyLink } from "../components/matches/MatchCard";
import { StatusControl } from "../components/matches/StatusControl";
import { useUpdateMatch } from "../hooks/useUpdateMatch";
import { formatAges, formatDeadline, formatGenders, formatUnion } from "../lib/format";
import { sourceColor, sourceName } from "../lib/sources";
import styles from "./CastingCallPage.module.css";

export function CastingCallPage() {
  const id = Number(useParams().id);
  const call = useQuery({
    queryKey: ["casting-call", id],
    queryFn: () => getCastingCall(id),
    enabled: Number.isInteger(id),
  });

  // A 401 is handled globally (back to login), so it isn't reported here.
  if (!Number.isInteger(id) || (call.isError && !isUnauthorized(call.error))) {
    const missing =
      !Number.isInteger(id) || (call.error instanceof ApiError && call.error.status === 404);
    return (
      <main className={styles.page}>
        <BackLink />
        <p role="alert" className={styles.notice}>
          {missing
            ? "This casting call doesn’t exist. It may have been removed when its email was reprocessed."
            : `Couldn’t load this casting call: ${call.error?.message}`}
        </p>
      </main>
    );
  }
  if (!call.data) {
    return (
      <main className={styles.page}>
        <BackLink />
        <p className={styles.notice}>Loading…</p>
      </main>
    );
  }

  const data = call.data;
  const source = sourceName(data.source_key);
  const deadline = formatDeadline(data.submission_deadline);
  const facts: [string, string | null][] = [
    ["Project type", data.project_type],
    ["Union", formatUnion(data.union_status)],
    ["Locations", data.seeking_locations.join("; ") || null],
    ["Deadline", data.submission_deadline ? (deadline.full ?? deadline.text) : null],
    [
      "Posted",
      data.posted_at
        ? new Date(data.posted_at).toLocaleDateString(undefined, { dateStyle: "medium" })
        : null,
    ],
    ["Tags", data.category_tag],
  ];

  return (
    <main className={styles.page}>
      <BackLink />
      <article className={styles.call} style={{ borderTopColor: sourceColor(data.source_key) }}>
        <span className={styles.badge} style={{ background: sourceColor(data.source_key) }}>
          {source}
        </span>
        <h1 className={styles.title}>{data.title}</h1>

        <dl className={styles.facts}>
          {facts
            .filter(([, value]) => value)
            .map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd className={label === "Deadline" && deadline.closed ? styles.closed : undefined}>
                  {label === "Deadline" && deadline.closed ? `Closed: ${value}` : value}
                </dd>
              </div>
            ))}
        </dl>

        {data.description && <p className={styles.description}>{data.description}</p>}
        {data.view_all_jobs_url && (
          <p className={styles.sourceLink}>
            <a href={data.view_all_jobs_url} target="_blank" rel="noopener noreferrer">
              View on {source} ↗
            </a>
          </p>
        )}
      </article>

      <h2 className={styles.rolesHeading}>
        {data.roles.length} {data.roles.length === 1 ? "role" : "roles"}
      </h2>
      <div className={styles.roles}>
        {data.roles.map((role) => (
          <RoleCard key={role.id} role={role} source={source} />
        ))}
      </div>
    </main>
  );
}

function BackLink() {
  return (
    <Link to="/" className={styles.back}>
      ← All matches
    </Link>
  );
}

function RoleCard({ role, source }: { role: RoleDetail; source: string }) {
  const update = useUpdateMatch();
  const match = role.saved_match;
  const ages = formatAges(role);
  const genders = formatGenders(role.genders);
  const details = [role.billing_type, genders, ages && `ages ${ages}`].filter(Boolean).join(" · ");

  return (
    <section className={styles.role} aria-labelledby={`role-${role.id}`} data-matched={!!match}>
      <div className={styles.roleTop}>
        <h3 id={`role-${role.id}`} className={styles.roleName}>
          {role.role_name}
        </h3>
        {role.apply_url && <ApplyLink href={role.apply_url} source={source} />}
      </div>
      {details && <p className={styles.roleDetails}>{details}</p>}
      <p className={styles.pay}>
        <span className={styles.payLabel}>Pay</span> {role.pay ?? "Not listed"}
      </p>

      {match ? (
        <>
          <StatusControl
            value={match.status}
            onChange={(status) => update.mutate({ id: match.id, patch: { status } })}
            disabled={update.isPending}
            label={`Status for ${role.role_name}`}
          />
          {match.applied_at && (
            <p className={styles.applied}>
              Applied{" "}
              {new Date(match.applied_at).toLocaleDateString(undefined, { dateStyle: "medium" })}
            </p>
          )}
          <NoteEditor
            key={match.user_note ?? ""}
            initial={match.user_note ?? ""}
            label={`Note for ${role.role_name}`}
            saving={update.isPending}
            onSave={(note) => update.mutate({ id: match.id, patch: { user_note: note || null } })}
          />
          {update.isError && (
            <p role="alert" className={styles.error}>
              Couldn’t save: {update.error.message}
            </p>
          )}
        </>
      ) : (
        <p className={styles.unmatched}>Doesn’t match your profile, so it isn’t tracked.</p>
      )}
    </section>
  );
}

function NoteEditor(props: {
  initial: string;
  label: string;
  saving: boolean;
  onSave: (note: string) => void;
}) {
  const [note, setNote] = useState(props.initial);
  const dirty = note.trim() !== props.initial.trim();
  return (
    <form
      className={styles.note}
      onSubmit={(e) => {
        e.preventDefault();
        props.onSave(note.trim());
      }}
    >
      <label className="visually-hidden" htmlFor={props.label}>
        {props.label}
      </label>
      <textarea
        id={props.label}
        rows={2}
        placeholder="Notes: self-tape due, sides received, callback…"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      {dirty && (
        <button type="submit" disabled={props.saving}>
          {props.saving ? "Saving…" : "Save note"}
        </button>
      )}
    </form>
  );
}
