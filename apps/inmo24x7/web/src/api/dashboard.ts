import { ApiRequestError, errorCode, type Dashboard } from "@followup/api-client-inmo24x7";

import { apiClient } from "./client";

export async function fetchDashboard(): Promise<Dashboard> {
  const { data, error, response } = await apiClient.GET("/dashboard");
  if (data) {
    return data;
  }
  throw new ApiRequestError(response.status, errorCode(error));
}
