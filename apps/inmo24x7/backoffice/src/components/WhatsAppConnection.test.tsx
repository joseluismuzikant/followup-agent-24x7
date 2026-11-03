import type { WhatsAppConnection } from "@followup/api-client-inmo24x7";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  WhatsAppRequestError,
  fetchConnection,
  runConnectionAction,
  saveConnection,
  sendTestMessage,
} from "../api/whatsapp";
import { WhatsAppConnectionPanel } from "./WhatsAppConnection";

vi.mock("../api/whatsapp", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/whatsapp")>()),
  fetchConnection: vi.fn(),
  saveConnection: vi.fn(),
  runConnectionAction: vi.fn(),
  sendTestMessage: vi.fn(),
}));

const connected: WhatsAppConnection = {
  status: "connected",
  display_phone_number: "+54 9 11 5555-0100",
  verified_name: "Inmobiliaria Sur",
  last_inbound_at: "2026-11-03T13:00:00Z",
  connected_at: "2026-11-02T12:00:00Z",
  phone_number_id: "123456",
  waba_id: "999",
  sender: "cloud",
  template_name: "hello_world",
  template_language: "en_US",
  last_error_code: null,
  updated_at: "2026-11-03T13:00:00Z",
  has_access_token: true,
};

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <WhatsAppConnectionPanel tenantId="t1" />
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

describe("WhatsAppConnectionPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("connects a new number with the token", async () => {
    vi.mocked(fetchConnection).mockResolvedValue({ status: "not_connected", has_access_token: false });
    vi.mocked(saveConnection).mockResolvedValue(connected);
    const user = renderPanel();

    await user.type(await screen.findByLabelText("Phone number ID"), "123456");
    await user.type(screen.getByLabelText("WABA ID"), "999");
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(screen.getByRole("alert").textContent).toContain("Pegá el token");
    expect(saveConnection).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Token de acceso"), "EAAG-token");
    await user.type(
      screen.getByLabelText("Plantilla de confirmación de visita"),
      "confirmacion_visita",
    );
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(saveConnection).toHaveBeenCalledWith("t1", {
      phone_number_id: "123456",
      waba_id: "999",
      display_phone_number: null,
      access_token: "EAAG-token",
      sender: "cloud",
      visit_template_name: "confirmacion_visita",
    });
    expect(await screen.findByText("Conectado")).toBeTruthy();
  });

  it("shows the status card and never the stored token", async () => {
    vi.mocked(fetchConnection).mockResolvedValue({
      ...connected,
      status: "error",
      last_error_code: "190",
    });
    renderPanel();

    expect(await screen.findByText("Error")).toBeTruthy();
    expect(screen.getByText("Código 190")).toBeTruthy();
    expect(screen.getByText("+54 9 11 5555-0100")).toBeTruthy();
    expect((screen.getByLabelText("Token de acceso") as HTMLInputElement).value).toBe("");
    expect(screen.getByText(/Ya hay un token guardado/)).toBeTruthy();
  });

  it("runs the actions and shows Meta's error code when one fails", async () => {
    vi.mocked(fetchConnection).mockResolvedValue(connected);
    vi.mocked(runConnectionAction).mockResolvedValue(connected);
    vi.mocked(sendTestMessage).mockRejectedValue(
      new WhatsAppRequestError(502, "whatsapp_api_error", "131030"),
    );
    const user = renderPanel();

    await user.click(await screen.findByRole("button", { name: "Probar conexión" }));
    expect(await screen.findByText(/La conexión funciona/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Suscribir la app" }));
    expect(runConnectionAction).toHaveBeenCalledWith("t1", "subscribe");

    await user.type(screen.getByLabelText("Enviar mensaje de prueba a"), "11 5555-0188");
    await user.click(screen.getByRole("button", { name: "Enviar mensaje de prueba" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Meta rechazó el pedido. Código de Meta: 131030.");
    expect(sendTestMessage).toHaveBeenCalledWith("t1", "11 5555-0188");

    await user.click(screen.getByRole("button", { name: "Desconectar" }));
    expect(runConnectionAction).toHaveBeenLastCalledWith("t1", "disconnect");
    expect(within(document.body).getByText(/quedó desconectado/)).toBeTruthy();
  });
});
