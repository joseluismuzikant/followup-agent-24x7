import { createApiClient, serverErrorInfo } from "@followup/api-client-inmo24x7";
import { reportServerError } from "@followup/observability";

import { getAccessToken } from "../lib/auth-adapter";

const baseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8001";

export const apiClient = createApiClient(baseUrl, {
  getAccessToken,
  onServerError: reportServerError,
});

/** For downloads openapi-fetch does not cover well (the Consumo CSV). */
export async function authorizedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = await getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const request = new Request(`${baseUrl.replace(/\/$/, "")}${path}`, { ...init, headers });
  const response = await fetch(request);
  if (response.status >= 500) {
    reportServerError(serverErrorInfo(request, response));
  }
  return response;
}
