import {
  ApiRequestError,
  errorCode,
  type TenantSettings,
  type TenantSettingsInput,
} from "@followup/api-client-inmo24x7";

import { apiClient } from "./client";

export async function fetchTenantSettings(): Promise<TenantSettings> {
  const { data, error, response } = await apiClient.GET("/tenant/settings");
  if (data) {
    return data;
  }
  throw new ApiRequestError(response.status, errorCode(error));
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
  throw new ApiRequestError(response.status, errorCode(error));
}
