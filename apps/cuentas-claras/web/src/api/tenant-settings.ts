import { apiError, type TenantSettings, type TenantSettingsInput } from "@followup/api-client-cuentas-claras";

import { apiClient } from "./client";

export async function fetchTenantSettings(): Promise<TenantSettings> {
  const { data, error, response } = await apiClient.GET("/tenant/settings");
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function saveTenantSettings(
  input: TenantSettingsInput,
): Promise<TenantSettings> {
  const { data, error, response } = await apiClient.PUT("/tenant/settings", {
    body: input,
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}
