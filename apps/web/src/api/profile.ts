import { ApiError, request } from "./client";
import type { Profile, ProfileInput } from "./types";

/** The profile, or null before one has been created (the API answers 404). */
export async function getProfile(): Promise<Profile | null> {
  try {
    return await request<Profile>("GET", "/profile");
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/** Saves the profile; the API re-runs matching before it answers. */
export const saveProfile = (profile: ProfileInput) =>
  request<Profile>("PUT", "/profile", { body: profile });
