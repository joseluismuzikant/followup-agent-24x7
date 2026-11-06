import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError, apiError, createApiClient } from "./api";
import { errorMessages } from "./errors";

describe("the shared API client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("adds the bearer token and reports 5xx answers", async () => {
    const fetch = vi.fn(
      async () =>
        new Response("{}", { status: 503, headers: { "X-Request-ID": "abcdef0123456789" } }),
    );
    vi.stubGlobal("fetch", fetch);
    const onServerError = vi.fn();
    const client = createApiClient<Record<string, never>>("https://api.example.com/", {
      getAccessToken: () => "token-1",
      onServerError,
    });

    await (client as unknown as { GET: (path: string) => Promise<unknown> }).GET("/me");

    const request = (fetch.mock.calls[0] as unknown as [Request])[0];
    expect(request.headers.get("Authorization")).toBe("Bearer token-1");
    expect(onServerError).toHaveBeenCalledWith({
      status: 503,
      method: "GET",
      path: "/me",
      requestId: "abcdef0123456789",
    });
  });

  it("turns failures into Spanish messages with the reference code", () => {
    const message = errorMessages({ invoice_not_found: "No encontramos esa factura." });
    const error = apiError(
      new Response(null, { status: 500, headers: { "X-Request-ID": "abcdef0123456789" } }),
      { code: "internal_error" },
    );

    expect(error.reference).toBe("abcdef01");
    expect(message(error, "x")).toBe(
      "Ocurrió un error inesperado. Probá de nuevo. Código de referencia: abcdef01.",
    );
    expect(message(new ApiRequestError(404, "invoice_not_found", "abc"), "x")).toBe(
      "No encontramos esa factura.",
    );
    expect(message(new Error("network"), "No pudimos.")).toBe("No pudimos.");
  });
});
