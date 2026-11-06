/**
 * The API client every panel uses (no React): openapi-fetch with the bearer token, a hook
 * for 5xx answers (Sentry) and the request id behind "Código de referencia". Each product's
 * generated client package passes its own `paths`.
 */
import createClient from "openapi-fetch";

export const REQUEST_ID_HEADER = "X-Request-ID";

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string;
  /** The API's X-Request-ID: the "código de referencia" a customer can report. */
  readonly requestId: string | null;

  constructor(status: number, code: string, requestId: string | null = null) {
    super(`API request failed (${status}): ${code}`);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }

  /** What the panels show as "Código de referencia": the first 8 characters. */
  get reference(): string | null {
    return this.requestId ? this.requestId.slice(0, 8) : null;
  }
}

export function errorCode(error: unknown): string {
  if (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    typeof error.code === "string"
  ) {
    return error.code;
  }
  return "unknown_error";
}

/** The error for a failed response, with its code and request id. */
export function apiError(response: Response, body: unknown): ApiRequestError {
  return new ApiRequestError(
    response.status,
    errorCode(body),
    response.headers.get(REQUEST_ID_HEADER),
  );
}

/** What the panels report about a 5xx: never bodies or query strings. */
export interface ServerErrorInfo {
  status: number;
  method: string;
  path: string;
  requestId: string | null;
}

export interface ApiClientOptions {
  getAccessToken?: () => string | null | undefined | Promise<string | null | undefined>;
  /** Called for every 5xx answer (the panels send it to Sentry). */
  onServerError?: (info: ServerErrorInfo) => void;
}

export function serverErrorInfo(request: Request, response: Response): ServerErrorInfo {
  return {
    status: response.status,
    method: request.method,
    path: new URL(request.url).pathname,
    requestId: response.headers.get(REQUEST_ID_HEADER),
  };
}

// eslint-disable-next-line @typescript-eslint/no-empty-object-type
export function createApiClient<Paths extends {}>(baseUrl: string, options: ApiClientOptions = {}) {
  return createClient<Paths>({
    baseUrl: baseUrl.replace(/\/$/, ""),
    fetch: async (request) => {
      const token = await options.getAccessToken?.();
      let outgoing = request;
      if (token) {
        const headers = new Headers(request.headers);
        headers.set("Authorization", `Bearer ${token}`);
        outgoing = new Request(request, { headers });
      }
      const response = await globalThis.fetch(outgoing);
      if (response.status >= 500) {
        options.onServerError?.(serverErrorInfo(outgoing, response));
      }
      return response;
    },
  });
}
