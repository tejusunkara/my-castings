import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { listRawEmails, reprocessRawEmail } from "../api/admin";
import type { RawEmail, ReprocessResult } from "../api/types";
import { sourceName } from "../lib/sources";
import styles from "./AdminPage.module.css";

const STATUS_LABELS: Record<RawEmail["parse_status"], string> = {
  pending: "Pending",
  success: "Parsed",
  partial: "Partly parsed",
  failed: "Failed",
};

export function AdminPage() {
  const [all, setAll] = useState(false);
  const emails = useQuery({
    queryKey: ["admin", "raw-emails", { all }],
    queryFn: () => listRawEmails(!all),
  });

  return (
    <main className={styles.page}>
      <h1 className={styles.heading}>Needs attention</h1>
      <p className={styles.intro}>
        Emails that failed to parse, parsed only partly, or came from a sender that couldn’t be
        verified. Unverified emails are quarantined: nothing from them reaches your matches. After a
        parser fix, reprocess an email to parse it again.
      </p>

      <div className={styles.tabs} role="group" aria-label="Which emails">
        <button type="button" aria-pressed={!all} onClick={() => setAll(false)}>
          Needs attention
        </button>
        <button type="button" aria-pressed={all} onClick={() => setAll(true)}>
          All emails
        </button>
      </div>

      {emails.isPending ? (
        <p className={styles.notice}>Loading…</p>
      ) : emails.isError ? (
        <p role="alert" className={styles.notice}>
          Couldn’t load emails: {emails.error.message}
        </p>
      ) : emails.data.length === 0 ? (
        <p className={styles.notice}>
          {all ? "No emails yet." : "Nothing needs attention. Every email parsed cleanly."}
        </p>
      ) : (
        <ul className={styles.list}>
          {emails.data.map((email) => (
            <EmailRow key={email.id} email={email} />
          ))}
        </ul>
      )}
    </main>
  );
}

function EmailRow({ email }: { email: RawEmail }) {
  const queryClient = useQueryClient();
  const reprocess = useMutation({
    mutationFn: () => reprocessRawEmail(email.id),
    onSuccess: () =>
      Promise.all(
        ["admin", "matches", "casting-call"].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key] }),
        ),
      ),
  });

  return (
    <li className={styles.email}>
      <div className={styles.top}>
        <div className={styles.badges}>
          <span className={styles.status} data-status={email.parse_status}>
            {STATUS_LABELS[email.parse_status]}
          </span>
          <span className={styles.verified} data-verified={email.sender_verified}>
            {email.sender_verified ? "Sender verified" : "Sender not verified"}
          </span>
          {email.source_key && (
            <span className={styles.source}>{sourceName(email.source_key)}</span>
          )}
        </div>
        <time className={styles.date} dateTime={email.received_at}>
          {new Date(email.received_at).toLocaleString(undefined, {
            dateStyle: "medium",
            timeStyle: "short",
          })}
        </time>
      </div>

      <p className={styles.subject}>{email.subject ?? "(no subject)"}</p>
      <p className={styles.from}>From {email.from_address ?? "unknown sender"}</p>
      {email.parse_error && <p className={styles.problem}>{email.parse_error}</p>}

      <div className={styles.actions}>
        <details className={styles.details}>
          <summary>Verification details</summary>
          <pre>{JSON.stringify(email.verdict_details, null, 2)}</pre>
          <p className={styles.location}>
            Stored at {email.s3_bucket}/{email.s3_key}
          </p>
        </details>
        <button
          type="button"
          className={styles.reprocess}
          onClick={() => reprocess.mutate()}
          disabled={reprocess.isPending}
        >
          {reprocess.isPending ? "Reprocessing…" : "Reprocess"}
        </button>
      </div>

      <div aria-live="polite">
        {reprocess.isSuccess && <p className={styles.result}>{describe(reprocess.data)}</p>}
        {reprocess.isError && (
          <p role="alert" className={styles.problem}>
            Couldn’t reprocess: {reprocess.error.message}
          </p>
        )}
      </div>
    </li>
  );
}

function describe(result: ReprocessResult): string {
  const parts = [
    `${STATUS_LABELS[result.raw_email.parse_status]}.`,
    `${result.created_roles} new, ${result.updated_roles} updated, ${result.deleted_roles} removed roles;`,
    `${result.new_matches} new matches.`,
  ];
  if (result.kept_role_ids.length) {
    parts.push(
      `${result.kept_role_ids.length} roles no longer in the email were kept because you acted on them.`,
    );
  }
  return parts.join(" ");
}
