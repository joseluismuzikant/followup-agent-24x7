import { createApiClient } from "@followup/api-client-cuentas-claras";
import { createAccountApi } from "@followup/app-shell";
import { reportServerError } from "@followup/observability";

import { getAccessToken } from "../lib/auth-adapter";

// Its own variable: both products read the same .env, and VITE_API_URL is inmo24x7's.
const baseUrl = import.meta.env.VITE_CUENTAS_CLARAS_API_URL ?? "http://localhost:8002";

export const apiClient = createApiClient(baseUrl, {
  getAccessToken,
  onServerError: reportServerError,
});

/** Sign-in and the forced password change (the same in every product). */
export const account = createAccountApi(baseUrl, getAccessToken);

