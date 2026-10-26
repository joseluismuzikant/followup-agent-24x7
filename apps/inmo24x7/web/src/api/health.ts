import {
  ApiRequestError,
  errorCode,
  type ReadinessResponse,
} from "@followup/api-client-inmo24x7";

import { apiClient } from "./client";

export async function fetchReadiness(): Promise<ReadinessResponse> {
  const { data, error, response } = await apiClient.GET("/health/ready");

  if (data) {
    return data;
  }

  throw new ApiRequestError(response.status, errorCode(error));
}
