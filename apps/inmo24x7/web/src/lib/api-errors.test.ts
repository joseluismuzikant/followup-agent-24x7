import { ApiRequestError, apiError, createApiClient } from "@followup/api-client-inmo24x7";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiErrorMessage } from "./api-errors";

const requestId = "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d";

describe("Código de referencia", () => {
  it("is added to unexpected failures: a 5xx or a code without a message", () => {
    expect(apiErrorMessage(new ApiRequestError(500, "internal_error", requestId), "x")).toBe(
      "Ocurrió un error inesperado. Probá de nuevo. Código de referencia: 1a2b3c4d.",
    );
    expect(apiErrorMessage(new ApiRequestError(400, "something_new", requestId), "No pudimos.")).toBe(
      "No pudimos. Código de referencia: 1a2b3c4d.",
    );
  });

  it("is not added to expected answers, or when there is no request id", () => {
    expect(apiErrorMessage(new ApiRequestError(404, "lead_not_found", requestId), "x")).toBe(
      "No encontramos esa consulta.",
    );
    expect(apiErrorMessage(new ApiRequestError(500, "internal_error"), "x")).toBe(
      "Ocurrió un error inesperado. Probá de nuevo.",
    );
  });

  it("comes from the response's X-Request-ID", () => {
    const response = new Response(null, { status: 503, headers: { "X-Request-ID": requestId } });

    const error = apiError(response, { code: "agent_unavailable" });

    expect([error.status, error.code, error.reference]).toEqual([503, "agent_unavailable", "1a2b3c4d"]);
  });
});

describe("API client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("reports 5xx answers with method, path and request id, never the query string", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (request: Request) =>
        new Response(JSON.stringify({ code: request.url.includes("boom") ? "internal_error" : "ok" }), {
          status: request.url.includes("boom") ? 500 : 404,
          headers: { "X-Request-ID": requestId, "Content-Type": "application/json" },
        }),
      ),
    );
    const onServerError = vi.fn();
    const client = createApiClient("https://api.example.com/", { onServerError });

    await client.GET("/leads", { params: { query: { q: "boom@example.com" } } });
    await client.GET("/dashboard");

    expect(onServerError).toHaveBeenCalledTimes(1);
    expect(onServerError).toHaveBeenCalledWith({
      status: 500,
      method: "GET",
      path: "/leads",
      requestId,
    });
  });
});
