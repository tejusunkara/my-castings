import type { AssetType } from "../api/types";

const MB = 1024 * 1024;
const IMAGES = ["image/jpeg", "image/png", "image/webp"];
const VIDEOS = ["video/mp4", "video/quicktime"];

export interface MediaKind {
  type: AssetType;
  title: string;
  hint: string;
  fileTypes: string[]; // empty: links only
  maxBytes: number;
  links: boolean;
  multiple: boolean; // pick several files at once
}

// Mirrors apps/api/app/services/media.py; the API and storage enforce the real limits.
export const MEDIA_KINDS: MediaKind[] = [
  {
    type: "headshot",
    title: "Headshots",
    hint: "JPEG, PNG or WebP, up to 25 MB.",
    fileTypes: IMAGES,
    maxBytes: 25 * MB,
    links: false,
    multiple: true,
  },
  {
    type: "digital",
    title: "Modeling digitals",
    hint: "Unretouched: front, profile, full length. JPEG, PNG or WebP, up to 25 MB.",
    fileTypes: IMAGES,
    maxBytes: 25 * MB,
    links: false,
    multiple: true,
  },
  {
    type: "acting_reel",
    title: "Acting reels",
    hint: "A Vimeo or YouTube link, or an MP4/MOV up to 2 GB.",
    fileTypes: VIDEOS,
    maxBytes: 2048 * MB,
    links: true,
    multiple: false,
  },
  {
    type: "self_tape",
    title: "Self-tapes",
    hint: "A link, or an MP4/MOV up to 2 GB.",
    fileTypes: VIDEOS,
    maxBytes: 2048 * MB,
    links: true,
    multiple: false,
  },
  {
    type: "resume",
    title: "Acting resume",
    hint: "PDF, up to 10 MB.",
    fileTypes: ["application/pdf"],
    maxBytes: 10 * MB,
    links: false,
    multiple: false,
  },
  {
    type: "social_link",
    title: "Social links",
    hint: "Instagram, TikTok, IMDb, your website…",
    fileTypes: [],
    maxBytes: 0,
    links: true,
    multiple: false,
  },
];

/** null when the file is acceptable, otherwise why not. */
export function fileProblem(kind: MediaKind, file: File): string | null {
  if (!kind.fileTypes.includes(file.type)) {
    return `${file.name} isn’t a supported file here. ${kind.hint}`;
  }
  if (file.size > kind.maxBytes) return `${file.name} is over ${formatBytes(kind.maxBytes)}.`;
  return null;
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1024 * MB) return `${(bytes / (1024 * MB)).toFixed(1)} GB`;
  if (bytes >= MB) return `${(bytes / MB).toFixed(bytes >= 10 * MB ? 0 : 1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** "vimeo.com" -> "Vimeo"; anything else: the host without "www.". */
export function linkSite(url: string): string {
  try {
    const host = new URL(url).hostname.replace(/^www\./, "");
    const known: Record<string, string> = {
      "vimeo.com": "Vimeo",
      "youtube.com": "YouTube",
      "youtu.be": "YouTube",
      "instagram.com": "Instagram",
      "tiktok.com": "TikTok",
      "imdb.com": "IMDb",
      "x.com": "X",
      "twitter.com": "X",
    };
    return known[host] ?? host;
  } catch {
    return url;
  }
}
