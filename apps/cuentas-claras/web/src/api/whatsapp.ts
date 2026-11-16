import { apiError } from "@followup/api-client-cuentas-claras";
import type {
  EmbeddedSignupInput,
  SignupAbandonedInput,
  WhatsAppError,
  WhatsAppStatus,
} from "@followup/api-client-cuentas-claras";
import { signupFailure } from "@followup/app-shell";
import type { WhatsAppPanelApi } from "@followup/app-shell";

import { apiClient } from "./client";

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

/** Read when called (tests replace this module's functions). */
export const panelApi: WhatsAppPanelApi = {
  completeEmbeddedSignup: (input) => completeEmbeddedSignup(input),
  retryEmbeddedSignup: () => retryEmbeddedSignup(),
  reportSignupAbandoned: (input) => reportSignupAbandoned(input),
};
