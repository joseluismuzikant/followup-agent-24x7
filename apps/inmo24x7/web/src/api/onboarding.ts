import {
  ApiRequestError,
  errorCode,
  type OnboardingState,
} from "@followup/api-client-inmo24x7";

import { apiClient } from "./client";

export async function fetchOnboarding(): Promise<OnboardingState> {
  const { data, error, response } = await apiClient.GET("/onboarding");
  if (data) {
    return data;
  }
  throw new ApiRequestError(response.status, errorCode(error));
}

export async function advanceOnboarding(toStep: string): Promise<OnboardingState> {
  const { data, error, response } = await apiClient.POST("/onboarding/advance", {
    body: { to_step: toStep },
  });
  if (data) {
    return data;
  }
  throw new ApiRequestError(response.status, errorCode(error));
}
