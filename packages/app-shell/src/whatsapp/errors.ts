import { ApiRequestError, errorCode, REQUEST_ID_HEADER } from "../api";
import type { WhatsAppError } from "./types";

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

export function signupFailure(response: Response, error: unknown): SignupRequestError {
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

/** A failed admin call with Meta's error code (admins see it). */
export class WhatsAppRequestError extends ApiRequestError {
  readonly metaCode: string | null;

  constructor(status: number, code: string, metaCode: string | null, requestId: string | null = null) {
    super(status, code, requestId);
    this.metaCode = metaCode;
  }
}

export function connectionFailure(response: Response, error: unknown): WhatsAppRequestError {
  const metaCode =
    typeof error === "object" && error !== null && "meta_code" in error
      ? String(error.meta_code)
      : null;
  return new WhatsAppRequestError(
    response.status,
    errorCode(error),
    metaCode,
    response.headers.get(REQUEST_ID_HEADER),
  );
}
