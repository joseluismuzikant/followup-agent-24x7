import { ApiRequestError, errorCode } from "@followup/api-client-inmo24x7";
import type {
  EmbeddedSignupInput,
  SignupAbandonedInput,
  WhatsAppError,
  WhatsAppStatus,
} from "@followup/api-client-inmo24x7";

import { apiClient } from "./client";

/** A failed Embedded Signup step, with Meta's error already in Spanish. */
export class SignupRequestError extends ApiRequestError {
  readonly translated: WhatsAppError | null;

  constructor(status: number, code: string, translated: WhatsAppError | null) {
    super(status, code);
    this.translated = translated;
  }
}

function signupFailure(status: number, error: unknown): SignupRequestError {
  const translated =
    typeof error === "object" && error !== null && "error" in error
      ? (error.error as WhatsAppError)
      : null;
  return new SignupRequestError(status, errorCode(error), translated);
}

export async function fetchWhatsAppStatus(): Promise<WhatsAppStatus> {
  const { data, error, response } = await apiClient.GET("/whatsapp");
  if (data) {
    return data;
  }
  throw new ApiRequestError(response.status, errorCode(error));
}

export async function completeEmbeddedSignup(input: EmbeddedSignupInput): Promise<WhatsAppStatus> {
  const { data, error, response } = await apiClient.POST("/whatsapp/embedded-signup", {
    body: input,
  });
  if (data) {
    return data;
  }
  throw signupFailure(response.status, error);
}

export async function retryEmbeddedSignup(): Promise<WhatsAppStatus> {
  const { data, error, response } = await apiClient.POST("/whatsapp/embedded-signup/retry");
  if (data) {
    return data;
  }
  throw signupFailure(response.status, error);
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
