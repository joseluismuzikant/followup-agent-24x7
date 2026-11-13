import { apiError } from "@followup/api-client-inmo24x7";
import type {
  EmbeddedSignupInput,
  SignupAbandonedInput,
  WhatsAppError,
  WhatsAppStatus,
} from "@followup/api-client-inmo24x7";
import { signupFailure } from "@followup/app-shell";

import { apiClient } from "./client";

/** A failed Embedded Signup step, with Meta's error already in Spanish (@followup/app-shell). */
export { SignupRequestError } from "@followup/app-shell";

export async function fetchWhatsAppStatus(): Promise<WhatsAppStatus> {
  const { data, error, response } = await apiClient.GET("/whatsapp");
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function completeEmbeddedSignup(input: EmbeddedSignupInput): Promise<WhatsAppStatus> {
  const { data, error, response } = await apiClient.POST("/whatsapp/embedded-signup", {
    body: input,
  });
  if (data) {
    return data;
  }
  throw signupFailure(response, error);
}

export async function retryEmbeddedSignup(): Promise<WhatsAppStatus> {
  const { data, error, response } = await apiClient.POST("/whatsapp/embedded-signup/retry");
  if (data) {
    return data;
  }
  throw signupFailure(response, error);
}

/** CANCEL / ERROR / FINISH_ONLY_WABA: recorded for support. Returns Meta's error code in
 * plain Spanish (null without a code, or if the report itself failed). */
export async function reportSignupAbandoned(
  input: SignupAbandonedInput,
): Promise<WhatsAppError | null> {
  try {
    const { data } = await apiClient.POST("/whatsapp/embedded-signup/abandoned", { body: input });
    return data?.error ?? null;
  } catch {
    return null;
  }
}
