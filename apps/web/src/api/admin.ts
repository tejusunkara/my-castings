import { request } from "./client";
import type { RawEmail, ReprocessResult } from "./types";

export const listRawEmails = (needsAttention: boolean) =>
  request<RawEmail[]>("GET", "/admin/raw-emails", {
    query: { needs_attention: needsAttention ? "true" : undefined, limit: 200 },
  });

export const reprocessRawEmail = (id: number) =>
  request<ReprocessResult>("POST", `/admin/raw-emails/${id}/reprocess`);
