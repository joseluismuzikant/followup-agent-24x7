import {
  ApiRequestError,
  errorCode,
  type MeResponse,
  type SignUpResponse,
} from "@followup/api-client-inmo24x7";

import { apiClient } from "./client";

export async function fetchMe(): Promise<MeResponse> {
  const { data, error, response } = await apiClient.GET("/me");

  if (data) {
    return data;
  }

  throw new ApiRequestError(response.status, errorCode(error));
}

export async function signUp(
  businessName: string,
  businessType: string,
): Promise<SignUpResponse> {
  const { data, error, response } = await apiClient.POST("/me/sign-up", {
    body: { business_name: businessName, business_type: businessType },
  });

  if (data) {
    return data;
  }

  throw new ApiRequestError(response.status, errorCode(error));
}
