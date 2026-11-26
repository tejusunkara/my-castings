import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useRef, useState, type FormEvent } from "react";

import {
  addLink,
  completeUpload,
  deleteMedia,
  listMedia,
  sendToStorage,
  startUpload,
  updateMedia,
} from "../api/media";
import type { MediaAsset } from "../api/types";
import { fileProblem, formatBytes, linkSite, MEDIA_KINDS, type MediaKind } from "../lib/media";
import styles from "./MediaPage.module.css";

const MEDIA_KEY = ["media"] as const;

interface Upload {
  id: string;
  name: string;
  progress: number;
  error: string | null;
}

export function MediaPage() {
  const media = useQuery({ queryKey: MEDIA_KEY, queryFn: listMedia });

  return (
    <main className={styles.page}>
      <h1 className={styles.heading}>Media</h1>
      <p className={styles.intro}>
        Everything you submit with: keep the ones you use today marked current, and move older ones
        to the archive. Files stay private to you.
      </p>
      {media.isPending ? (
        <p className={styles.notice}>Loading…</p>
      ) : media.isError ? (
        <p role="alert" className={styles.notice}>
          Couldn’t load your media: {media.error.message}
        </p>
      ) : (
        MEDIA_KINDS.map((kind) => (
          <MediaSection
            key={kind.type}
            kind={kind}
            assets={media.data.filter((a) => a.asset_type === kind.type)}
          />
        ))
      )}
    </main>
  );
}

function MediaSection({ kind, assets }: { kind: MediaKind; assets: MediaAsset[] }) {
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [problems, setProblems] = useState<string[]>([]);
  const headingId = useId();

  const current = assets.filter((a) => a.is_current);
  const archived = assets.filter((a) => !a.is_current);
  const patchUpload = (id: string, patch: Partial<Upload>) =>
    setUploads((list) => list.map((u) => (u.id === id ? { ...u, ...patch } : u)));

  async function upload(file: File) {
    const id = `${file.name}-${crypto.randomUUID()}`;
    setUploads((list) => [...list, { id, name: file.name, progress: 0, error: null }]);
    let assetId: number | null = null;
    try {
      const started = await startUpload({
        asset_type: kind.type,
        filename: file.name,
        content_type: file.type,
        size_bytes: file.size,
      });
      assetId = started.asset.id;
      await sendToStorage(started.upload, file, (progress) => patchUpload(id, { progress }));
      await completeUpload(assetId);
      setUploads((list) => list.filter((u) => u.id !== id));
    } catch (error) {
      patchUpload(id, { error: error instanceof Error ? error.message : String(error) });
      // Don't leave a half-made item behind; the media sweep catches anything this misses.
      if (assetId !== null) await deleteMedia(assetId).catch(() => {});
    } finally {
      await queryClient.invalidateQueries({ queryKey: MEDIA_KEY });
    }
  }

  function onFiles(files: FileList | null) {
    const picked = Array.from(files ?? []);
    const issues = picked.map((f) => fileProblem(kind, f)).filter((p): p is string => !!p);
    setProblems(issues);
    picked.filter((f) => !fileProblem(kind, f)).forEach(upload);
    if (fileInput.current) fileInput.current.value = "";
  }

  return (
    <section className={styles.section} aria-labelledby={headingId}>
      <div className={styles.sectionTop}>
        <div>
          <h2 id={headingId} className={styles.sectionTitle}>
            {kind.title}
          </h2>
          <p className={styles.hint}>{kind.hint}</p>
        </div>
        {kind.fileTypes.length > 0 && (
          <>
            <input
              ref={fileInput}
              type="file"
              className="visually-hidden"
              id={`${headingId}-file`}
              accept={kind.fileTypes.join(",")}
              multiple={kind.multiple}
              onChange={(e) => onFiles(e.target.files)}
            />
            <label htmlFor={`${headingId}-file`} className={styles.uploadButton}>
              Upload {kind.multiple ? "files" : "a file"}
              <span className="visually-hidden"> to {kind.title}</span>
            </label>
          </>
        )}
      </div>

      {kind.links && <LinkForm kind={kind} />}

      {problems.map((p) => (
        <p key={p} role="alert" className={styles.error}>
          {p}
        </p>
      ))}

      {uploads.length > 0 && (
        <ul className={styles.uploads} aria-label={`Uploads to ${kind.title}`}>
          {uploads.map((u) => (
            <li key={u.id}>
              <span className={styles.uploadName}>{u.name}</span>
              {u.error ? (
                <span role="alert" className={styles.error}>
                  Upload failed: {u.error}{" "}
                  <button
                    type="button"
                    className={styles.textButton}
                    onClick={() => setUploads((list) => list.filter((x) => x.id !== u.id))}
                  >
                    Dismiss
                  </button>
                </span>
              ) : (
                <progress max={1} value={u.progress} aria-label={`Uploading ${u.name}`} />
              )}
            </li>
          ))}
        </ul>
      )}

      {current.length === 0 && uploads.length === 0 ? (
        <p className={styles.empty}>Nothing current yet.</p>
      ) : (
        <ul className={styles.grid}>
          {current.map((asset) => (
            <MediaItem key={asset.id} asset={asset} />
          ))}
        </ul>
      )}

      {archived.length > 0 && (
        <details className={styles.archive}>
          <summary>Archive ({archived.length})</summary>
          <ul className={styles.grid}>
            {archived.map((asset) => (
              <MediaItem key={asset.id} asset={asset} />
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function LinkForm({ kind }: { kind: MediaKind }) {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState("");
  const [label, setLabel] = useState("");
  const id = useId();
  const add = useMutation({
    mutationFn: () => addLink({ asset_type: kind.type, url: url.trim(), label: label || null }),
    onSuccess: () => {
      setUrl("");
      setLabel("");
      return queryClient.invalidateQueries({ queryKey: MEDIA_KEY });
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (url.trim()) add.mutate();
  }

  return (
    <form className={styles.linkForm} onSubmit={onSubmit}>
      <label className="visually-hidden" htmlFor={`${id}-url`}>
        Link for {kind.title}
      </label>
      <input
        id={`${id}-url`}
        type="url"
        inputMode="url"
        placeholder="https://…"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
      />
      <label className="visually-hidden" htmlFor={`${id}-label`}>
        Label (optional)
      </label>
      <input
        id={`${id}-label`}
        className={styles.labelInput}
        placeholder="Label (optional)"
        value={label}
        onChange={(e) => setLabel(e.target.value)}
      />
      <button type="submit" disabled={!url.trim() || add.isPending}>
        Add link
      </button>
      {add.isError && (
        <p role="alert" className={styles.error}>
          {add.error.message}
        </p>
      )}
    </form>
  );
}

function MediaItem({ asset }: { asset: MediaAsset }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [label, setLabel] = useState(asset.label ?? "");
  const refresh = () => queryClient.invalidateQueries({ queryKey: MEDIA_KEY });
  const update = useMutation({
    mutationFn: (patch: { label?: string | null; is_current?: boolean }) =>
      updateMedia(asset.id, patch),
    onSuccess: () => {
      setEditing(false);
      return refresh();
    },
  });
  const remove = useMutation({ mutationFn: () => deleteMedia(asset.id), onSuccess: refresh });

  const name =
    asset.label ||
    asset.original_filename ||
    (asset.external_url ? linkSite(asset.external_url) : "Untitled");
  const details = [
    asset.external_url ? linkSite(asset.external_url) : asset.original_filename,
    asset.file_size_bytes ? formatBytes(asset.file_size_bytes) : null,
    new Date(asset.created_at).toLocaleDateString(undefined, { dateStyle: "medium" }),
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <li className={styles.item} data-current={asset.is_current}>
      <Preview asset={asset} />
      <div className={styles.itemBody}>
        {editing ? (
          <form
            className={styles.rename}
            onSubmit={(e) => {
              e.preventDefault();
              update.mutate({ label: label.trim() || null });
            }}
          >
            <label className="visually-hidden" htmlFor={`label-${asset.id}`}>
              Label
            </label>
            <input
              id={`label-${asset.id}`}
              value={label}
              placeholder="e.g. Commercial, Theatrical"
              autoFocus
              onChange={(e) => setLabel(e.target.value)}
            />
            <button type="submit" disabled={update.isPending}>
              Save
            </button>
          </form>
        ) : (
          <p className={styles.itemName}>{name}</p>
        )}
        <p className={styles.itemDetails}>{details}</p>
        {asset.upload_status === "pending" && <p className={styles.itemDetails}>Uploading…</p>}
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.textButton}
            onClick={() => update.mutate({ is_current: !asset.is_current })}
            disabled={update.isPending}
          >
            {asset.is_current ? "Move to archive" : "Make current"}
          </button>
          {!editing && (
            <button type="button" className={styles.textButton} onClick={() => setEditing(true)}>
              {asset.label ? "Rename" : "Add label"}
            </button>
          )}
          <button
            type="button"
            className={`${styles.textButton} ${styles.danger}`}
            disabled={remove.isPending}
            onClick={() => window.confirm(`Delete “${name}” for good?`) && remove.mutate()}
          >
            Delete
          </button>
        </div>
        {(update.isError || remove.isError) && (
          <p role="alert" className={styles.error}>
            {(update.error ?? remove.error)?.message}
          </p>
        )}
      </div>
    </li>
  );
}

function Preview({ asset }: { asset: MediaAsset }) {
  if (asset.external_url) {
    return (
      <a
        className={`${styles.preview} ${styles.linkPreview}`}
        href={asset.external_url}
        target="_blank"
        rel="noopener noreferrer"
      >
        {linkSite(asset.external_url)} ↗
      </a>
    );
  }
  if (!asset.view_url) return <div className={styles.preview} aria-hidden="true" />;
  if (asset.content_type?.startsWith("image/")) {
    return (
      <a className={styles.preview} href={asset.view_url} target="_blank" rel="noopener noreferrer">
        <img
          src={asset.view_url}
          alt={asset.label ?? asset.original_filename ?? ""}
          loading="lazy"
        />
      </a>
    );
  }
  if (asset.content_type?.startsWith("video/")) {
    return (
      <video className={styles.preview} src={asset.view_url} controls preload="metadata">
        <track kind="captions" />
      </video>
    );
  }
  return (
    <a
      className={`${styles.preview} ${styles.linkPreview}`}
      href={asset.view_url}
      target="_blank"
      rel="noopener noreferrer"
    >
      Open PDF ↗
    </a>
  );
}
