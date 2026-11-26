import { request } from "./client";
import type { AssetType, MediaAsset, UploadStarted } from "./types";

export const listMedia = () => request<MediaAsset[]>("GET", "/media");

export const startUpload = (body: {
  asset_type: AssetType;
  filename: string;
  content_type: string;
  size_bytes: number;
  label?: string | null;
}) => request<UploadStarted>("POST", "/media/uploads", { body });

export const completeUpload = (id: number) => request<MediaAsset>("POST", `/media/${id}/complete`);

export const addLink = (body: { asset_type: AssetType; url: string; label?: string | null }) =>
  request<MediaAsset>("POST", "/media/links", { body });

export const updateMedia = (id: number, patch: { label?: string | null; is_current?: boolean }) =>
  request<MediaAsset>("PATCH", `/media/${id}`, { body: patch });

export const deleteMedia = (id: number) => request<void>("DELETE", `/media/${id}`);

/**
 * Sends a file to storage with the signed form from startUpload: every form field first,
 * the file last (S3 ignores fields after the file). XMLHttpRequest rather than fetch,
 * because only it reports upload progress.
 */
export function sendToStorage(
  form: UploadStarted["upload"],
  file: File,
  onProgress: (fraction: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const body = new FormData();
    for (const [name, value] of Object.entries(form.fields)) body.append(name, value);
    body.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", form.url);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve()
        : reject(new Error(storageError(xhr.responseText) ?? `storage answered ${xhr.status}`));
    xhr.onerror = () => reject(new Error("couldn’t reach storage"));
    xhr.send(body);
  });
}

/** S3 errors are XML: <Error><Code>EntityTooLarge</Code><Message>…</Message></Error>. */
function storageError(xml: string): string | null {
  const code = xml.match(/<Code>([^<]+)<\/Code>/)?.[1];
  if (code === "EntityTooLarge") return "the file is larger than this type allows";
  return xml.match(/<Message>([^<]+)<\/Message>/)?.[1] ?? null;
}
