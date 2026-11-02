import { createApiClient } from "@followup/api-client-inmo24x7";

import { getAccessToken } from "../lib/auth-adapter";

const baseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8001";

export const apiClient = createApiClient(baseUrl, { getAccessToken });

/** For requests openapi-fetch does not cover well: file uploads and CSV downloads. */
export async function authorizedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = await getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return fetch(`${baseUrl.replace(/\/$/, "")}${path}`, { ...init, headers });
}
