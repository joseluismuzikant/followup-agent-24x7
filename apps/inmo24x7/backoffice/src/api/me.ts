import {
  ApiRequestError,
  errorCode,
  type MeResponse,
} from "@followup/api-client-inmo24x7";

import { apiClient } from "./client";

export async function fetchMe(): Promise<MeResponse> {
  const { data, error, response } = await apiClient.GET("/me");

  if (data) {
    return data;
  }

  throw new ApiRequestError(response.status, errorCode(error));
}
