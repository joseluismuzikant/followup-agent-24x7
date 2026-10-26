import {
  ApiRequestError,
  errorCode,
  type TenantPage,
} from "@followup/api-client-inmo24x7";

import { apiClient } from "./client";

export async function fetchTenants(page: number, limit: number): Promise<TenantPage> {
  const { data, error, response } = await apiClient.GET("/tenants", {
    params: { query: { page, limit } },
  });

  if (data) {
    return data;
  }

  throw new ApiRequestError(response.status, errorCode(error));
}
