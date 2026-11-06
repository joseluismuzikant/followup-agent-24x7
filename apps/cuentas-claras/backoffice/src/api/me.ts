import { apiError, type MeResponse } from "@followup/api-client-cuentas-claras";

import { identify } from "@followup/observability";

import { apiClient } from "./client";

export async function fetchMe(): Promise<MeResponse> {
  const { data, error, response } = await apiClient.GET("/me");

  if (data) {
    // Error reports carry the profile id (never the email).
    identify(data.profile.id);
    return data;
  }

  throw apiError(response, error);
}
