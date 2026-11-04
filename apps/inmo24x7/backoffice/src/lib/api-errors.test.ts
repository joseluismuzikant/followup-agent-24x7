import { ApiRequestError } from "@followup/api-client-inmo24x7";
import { describe, expect, it } from "vitest";

import { WhatsAppRequestError } from "../api/whatsapp";
import { apiErrorMessage } from "./api-errors";

describe("apiErrorMessage", () => {
  it("adds the reference code to unexpected failures, after Meta's code", () => {
    expect(apiErrorMessage(new ApiRequestError(500, "internal_error", "abcdef0123456789"), "x")).toBe(
      "Ocurrió un error inesperado. Probá de nuevo. Código de referencia: abcdef01.",
    );
    expect(
      apiErrorMessage(new WhatsAppRequestError(502, "whatsapp_api_error", "131030", "abcdef0123"), "x"),
    ).toBe("Meta rechazó el pedido. Código de Meta: 131030. Código de referencia: abcdef01.");
  });

  it("leaves expected answers alone", () => {
    expect(apiErrorMessage(new ApiRequestError(404, "tenant_not_found", "abcdef0123"), "x")).toBe(
      "No encontramos ese negocio.",
    );
  });
});
