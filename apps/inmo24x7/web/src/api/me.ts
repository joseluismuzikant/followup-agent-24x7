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

/** Joins the business an admin created for the signed-in email ("Dar de alta"). */
export async function signUp(): Promise<SignUpResponse> {
  const { data, error, response } = await apiClient.POST("/me/sign-up");

  if (data) {
    return data;
  }

  throw apiError(response, error);
}
