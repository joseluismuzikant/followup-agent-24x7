import { apiError, type MeResponse, type SignUpResponse } from "@followup/api-client-inmo24x7";

import { identify } from "@followup/observability";

import { apiClient } from "./client";

export async function fetchMe(): Promise<MeResponse> {
  const { data, error, response } = await apiClient.GET("/me");

  if (data) {
    // Error reports carry the profile id (never the email) and the business.
    identify(data.profile.id, data.tenant?.id);
    return data;
  }

  throw apiError(response, error);
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

  throw apiError(response, error);
}
