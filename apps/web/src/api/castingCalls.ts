import { request } from "./client";
import type { CastingCall } from "./types";

export const getCastingCall = (id: number) => request<CastingCall>("GET", `/casting-calls/${id}`);
