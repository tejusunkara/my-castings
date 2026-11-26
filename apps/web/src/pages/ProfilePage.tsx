import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";

import { getProfile, saveProfile } from "../api/profile";
import type { Profile, ProfileInput } from "../api/types";
import { toggle } from "../lib/filters";
import styles from "./ProfilePage.module.css";

// Common role gender labels. Matching compares lower-cased labels, treating "woman" as
// "female" and ignoring hyphens, so these cover how the three sources write them.
const GENDER_OPTIONS = [
  "female",
  "male",
  "non-binary",
  "trans female",
  "trans male",
  "femme presenting",
  "masculine presenting",
];

const EMPTY: ProfileInput = {
  display_name: null,
  date_of_birth: null,
  playing_age_min: null,
  playing_age_max: null,
  genders: [],
  location_city: null,
  location_state: null,
  union_status: null,
  bio: null,
  willing_to_travel: false,
};

export function ProfilePage() {
  const profile = useQuery({ queryKey: ["profile"], queryFn: getProfile });

  return (
    <main className={styles.page}>
      <h1 className={styles.heading}>Profile</h1>
      <p className={styles.intro}>
        Matching uses your playing ages, genders and location. Saving re-checks every role straight
        away; roles you’ve saved, applied to or dismissed keep their status.
      </p>
      {profile.isPending ? (
        <p className={styles.notice}>Loading…</p>
      ) : profile.isError ? (
        <p role="alert" className={styles.notice}>
          Couldn’t load your profile: {profile.error.message}
        </p>
      ) : (
        <ProfileForm profile={profile.data} />
      )}
    </main>
  );
}

function toInput(profile: Profile | null): ProfileInput {
  if (!profile) return EMPTY;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- drop server-only fields
  const { id, updated_at, ...input } = profile;
  return input;
}

const blankToNull = (value: string) => (value.trim() === "" ? null : value.trim());
const numberOrNull = (value: string) => (value.trim() === "" ? null : Number(value));

/** Starts from the profile as first loaded and keeps its own state after saving. */
function ProfileForm({ profile }: { profile: Profile | null }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ProfileInput>(() => toInput(profile));
  const [customGender, setCustomGender] = useState("");
  const set = <K extends keyof ProfileInput>(key: K, value: ProfileInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const save = useMutation({
    mutationFn: saveProfile,
    onSuccess: (saved) => {
      queryClient.setQueryData(["profile"], saved);
      return queryClient.invalidateQueries({ queryKey: ["matches"] });
    },
  });

  const rangeError =
    (form.playing_age_min === null) !== (form.playing_age_max === null)
      ? "Set both ages, or neither."
      : form.playing_age_min !== null &&
          form.playing_age_max !== null &&
          form.playing_age_min > form.playing_age_max
        ? "The lower age can’t be above the upper one."
        : null;
  const stateError =
    form.location_state && !/^[A-Za-z]{2}$/.test(form.location_state)
      ? "Use the two-letter code, e.g. NY."
      : null;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (rangeError || stateError) return;
    save.mutate({ ...form, location_state: form.location_state?.toUpperCase() ?? null });
  }

  const extraGenders = form.genders.filter((g) => !GENDER_OPTIONS.includes(g));
  function addCustomGender() {
    const label = customGender.trim().toLowerCase();
    if (label && !form.genders.includes(label)) set("genders", [...form.genders, label]);
    setCustomGender("");
  }

  return (
    <form className={styles.form} onSubmit={onSubmit} noValidate>
      <fieldset className={styles.section}>
        <legend>Matching</legend>

        <div className={styles.row}>
          <Field label="Playing age from" error={rangeError}>
            {(id, describedBy) => (
              <input
                id={id}
                type="number"
                min={0}
                max={120}
                inputMode="numeric"
                value={form.playing_age_min ?? ""}
                aria-invalid={!!rangeError}
                aria-describedby={describedBy}
                onChange={(e) => set("playing_age_min", numberOrNull(e.target.value))}
              />
            )}
          </Field>
          <Field label="Playing age to">
            {(id) => (
              <input
                id={id}
                type="number"
                min={0}
                max={120}
                inputMode="numeric"
                value={form.playing_age_max ?? ""}
                aria-invalid={!!rangeError}
                onChange={(e) => set("playing_age_max", numberOrNull(e.target.value))}
              />
            )}
          </Field>
        </div>

        <div className={styles.group} role="group" aria-labelledby="genders-label">
          <span id="genders-label" className={styles.label}>
            Genders you’re open to playing
          </span>
          <p className={styles.hint}>Roles open to any gender always match.</p>
          <div className={styles.checks}>
            {[...GENDER_OPTIONS, ...extraGenders].map((label) => (
              <label key={label} className={styles.check}>
                <input
                  type="checkbox"
                  checked={form.genders.includes(label)}
                  onChange={() => set("genders", toggle(form.genders, label))}
                />
                {label}
              </label>
            ))}
          </div>
          <div className={styles.addRow}>
            <label className="visually-hidden" htmlFor="custom-gender">
              Another gender label
            </label>
            <input
              id="custom-gender"
              placeholder="Another label, as castings write it"
              value={customGender}
              onChange={(e) => setCustomGender(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addCustomGender();
                }
              }}
            />
            <button type="button" className={styles.secondary} onClick={addCustomGender}>
              Add
            </button>
          </div>
        </div>

        <div className={styles.row}>
          <Field label="City">
            {(id) => (
              <input
                id={id}
                autoComplete="address-level2"
                value={form.location_city ?? ""}
                onChange={(e) => set("location_city", blankToNull(e.target.value))}
              />
            )}
          </Field>
          <Field label="State" error={stateError} narrow>
            {(id, describedBy) => (
              <input
                id={id}
                maxLength={2}
                autoComplete="address-level1"
                value={form.location_state ?? ""}
                aria-invalid={!!stateError}
                aria-describedby={describedBy}
                onChange={(e) => set("location_state", blankToNull(e.target.value))}
              />
            )}
          </Field>
        </div>

        <label className={styles.check}>
          <input
            type="checkbox"
            checked={form.willing_to_travel}
            onChange={(e) => set("willing_to_travel", e.target.checked)}
          />
          Willing to travel (match roles in any location)
        </label>
      </fieldset>

      <fieldset className={styles.section}>
        <legend>About you</legend>
        <div className={styles.row}>
          <Field label="Name">
            {(id) => (
              <input
                id={id}
                autoComplete="name"
                value={form.display_name ?? ""}
                onChange={(e) => set("display_name", blankToNull(e.target.value))}
              />
            )}
          </Field>
          <Field label="Union status">
            {(id) => (
              <input
                id={id}
                placeholder="e.g. Non-union, SAG-AFTRA eligible"
                value={form.union_status ?? ""}
                onChange={(e) => set("union_status", blankToNull(e.target.value))}
              />
            )}
          </Field>
        </div>
        <Field
          label="Date of birth"
          hint="For your reference only. Matching uses your playing ages."
        >
          {(id, describedBy) => (
            <input
              id={id}
              type="date"
              value={form.date_of_birth ?? ""}
              aria-describedby={describedBy}
              onChange={(e) => set("date_of_birth", blankToNull(e.target.value))}
            />
          )}
        </Field>
        <Field label="Bio">
          {(id) => (
            <textarea
              id={id}
              rows={4}
              value={form.bio ?? ""}
              onChange={(e) => set("bio", blankToNull(e.target.value))}
            />
          )}
        </Field>
      </fieldset>

      <div className={styles.actions}>
        <button type="submit" className={styles.primary} disabled={save.isPending}>
          {save.isPending ? "Saving…" : profile ? "Save profile" : "Create profile"}
        </button>
        <p aria-live="polite" className={styles.status}>
          {save.isSuccess && "Saved. Matches are updated."}
        </p>
        {save.isError && (
          <p role="alert" className={styles.error}>
            Couldn’t save: {save.error.message}
          </p>
        )}
      </div>
    </form>
  );
}

function Field({
  label,
  hint,
  error,
  narrow,
  children,
}: {
  label: string;
  hint?: string;
  error?: string | null;
  narrow?: boolean;
  children: (id: string, describedBy: string | undefined) => ReactNode;
}) {
  const id = `field-${label.toLowerCase().replace(/\W+/g, "-")}`;
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <div className={narrow ? `${styles.field} ${styles.narrow}` : styles.field}>
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>
      {children(id, describedBy)}
      {hint && !error && (
        <p id={`${id}-hint`} className={styles.hint}>
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className={styles.error}>
          {error}
        </p>
      )}
    </div>
  );
}
