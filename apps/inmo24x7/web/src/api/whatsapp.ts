import { apiError, ApiRequestError, errorCode, REQUEST_ID_HEADER } from "@followup/api-client-inmo24x7";
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

  constructor(
    status: number,
    code: string,
    translated: WhatsAppError | null,
    requestId: string | null = null,
  ) {
    super(status, code, requestId);
    this.translated = translated;
  }
}

function signupFailure(response: Response, error: unknown): SignupRequestError {
  const translated =
    typeof error === "object" && error !== null && "error" in error
      ? (error.error as WhatsAppError)
      : null;
  return new SignupRequestError(
    response.status,
    errorCode(error),
    translated,
    response.headers.get(REQUEST_ID_HEADER),
  );
}

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
