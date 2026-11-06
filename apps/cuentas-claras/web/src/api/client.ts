import { createApiClient, serverErrorInfo } from "@followup/api-client-cuentas-claras";
import { createAccountApi } from "@followup/app-shell";
import { reportServerError } from "@followup/observability";

import { getAccessToken } from "../lib/auth-adapter";

// Its own variable: both products read the same .env, and VITE_API_URL is inmo24x7's.
const baseUrl = import.meta.env.VITE_CUENTAS_CLARAS_API_URL ?? "http://localhost:8002";

export const apiClient = createApiClient(baseUrl, {
  getAccessToken,
  onServerError: reportServerError,
});

/** Sign-in, the invitation link and the password change (the same in every product). */
export const account = createAccountApi(baseUrl, getAccessToken);

/** For requests openapi-fetch does not cover well: file uploads and CSV downloads. */
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
