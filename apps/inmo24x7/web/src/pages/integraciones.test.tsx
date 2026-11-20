import { ApiRequestError } from "@followup/api-client-inmo24x7";
import type { Integrations } from "@followup/api-client-inmo24x7";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  connectTokko,
  fetchIntegrations,
  saveWebhook,
  saveWidget,
  syncTokko,
  testWebhook,
} from "../api/integrations";
import { fetchMe } from "../api/me";
import { me } from "../test-fixtures";
import { IntegracionesPage } from "./integraciones";

vi.mock("../api/me", () => ({ fetchMe: vi.fn() }));
vi.mock("../api/integrations", () => ({
  fetchIntegrations: vi.fn(),
  connectTokko: vi.fn(),
  updateTokko: vi.fn(),
  disconnectTokko: vi.fn(),
  syncTokko: vi.fn(),
  saveWebhook: vi.fn(),
  rotateWebhookSecret: vi.fn(),
  deleteWebhook: vi.fn(),
  testWebhook: vi.fn(),
  saveWidget: vi.fn(),
}));

function integrations(overrides: Partial<Integrations> = {}): Integrations {
  return {
    tokko: {
      connected: false,
      import_properties: true,
      send_leads: true,
      last_sync_at: null,
      last_sync_status: null,
      last_error_code: null,
      last_report: null,
      deliveries: [],
    },
    webhook: {
      configured: false,
      enabled: false,
      url: null,
      has_secret: false,
      last_delivery_at: null,
      last_delivery_status: null,
      deliveries: [],
    },
    widget: {
      public_id: "AbC123xyz",
      enabled: true,
      color: "#047857",
      text_color: "#ffffff",
      position: "right",
      label: "Consultar por WhatsApp",
      whatsapp_connected: true,
    },
    ...overrides,
  };
}

const CONNECTED: Integrations["tokko"] = {
  connected: true,
  import_properties: true,
  send_leads: true,
  last_sync_at: "2026-11-19T12:00:00Z",
  last_sync_status: "ok",
  last_error_code: null,
  last_report: {
    started_at: "2026-11-19T12:00:00Z",
    finished_at: "2026-11-19T12:00:05Z",
    created: 18,
    updated: 2,
    paused: 1,
    unchanged: 0,
    failed: [{ external_id: "103", title: "Casa en Tigre", reason: "no tiene precio publicado." }],
    error_code: null,
  },
  deliveries: [],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/configuracion/integraciones"]}>
        <IntegracionesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

describe("Configuración → Integraciones", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchMe).mockResolvedValue(me("owner"));
    vi.mocked(fetchIntegrations).mockResolvedValue(integrations());
  });

  it("connects Tokko with the key and explains a wrong one", async () => {
    vi.mocked(connectTokko)
      .mockRejectedValueOnce(new ApiRequestError(422, "tokko_key_invalid"))
      .mockResolvedValueOnce(integrations({ tokko: CONNECTED }));
    const user = renderPage();
    await screen.findByText("Tokko Broker");
    const card = within(document.querySelector("#tokko") as HTMLElement);

    await user.type(card.getByLabelText("Clave API de Tokko"), "mala-clave-123");
    await user.click(card.getByRole("button", { name: "Probar conexión" }));
    expect((await card.findByRole("alert")).textContent).toContain("Tokko no aceptó esa clave");

    await user.clear(card.getByLabelText("Clave API de Tokko"));
    await user.type(card.getByLabelText("Clave API de Tokko"), "clave-buena-123");
    await user.click(card.getByRole("button", { name: "Probar conexión" }));

    expect(connectTokko).toHaveBeenLastCalledWith("clave-buena-123");
    expect(await card.findByText("Conectado")).toBeTruthy();
    expect(card.getByText(/18 nuevas · 2 actualizadas · 1 pausadas/)).toBeTruthy();
    expect(card.getByText("1 propiedad no se pudo importar")).toBeTruthy();
    expect(card.queryByLabelText("Clave API de Tokko")).toBeNull();
  });

  it("syncs now and shows that it is on its way", async () => {
    vi.mocked(fetchIntegrations).mockResolvedValue(integrations({ tokko: CONNECTED }));
    vi.mocked(syncTokko).mockResolvedValue(
      integrations({ tokko: { ...CONNECTED, last_sync_status: "queued" } }),
    );
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Sincronizar ahora" }));

    expect(await screen.findByText("Sincronizando con Tokko…")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "Sincronizando..." }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("shows the webhook secret once and the result of a test", async () => {
    vi.mocked(saveWebhook).mockResolvedValue({
      webhook: { ...integrations().webhook, configured: true, enabled: true, has_secret: true },
      secret: "whsec_secreto",
    });
    vi.mocked(testWebhook).mockResolvedValue({
      id: "d1",
      provider: "webhook",
      event: "ping",
      status: "delivered",
      attempts: 1,
      status_code: 200,
      error_code: null,
      lead_id: null,
      created_at: "2026-11-19T12:00:00Z",
      delivered_at: "2026-11-19T12:00:00Z",
    });
    const user = renderPage();
    const url = await screen.findByLabelText("Dirección (https://)");
    vi.mocked(fetchIntegrations).mockResolvedValue(
      integrations({
        webhook: { ...integrations().webhook, configured: true, enabled: true, has_secret: true },
      }),
    );

    await user.type(url, "https://hooks.zapier.com/x");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(saveWebhook).toHaveBeenCalledWith("https://hooks.zapier.com/x", true);
    expect(await screen.findByText("whsec_secreto")).toBeTruthy();
    expect(screen.getByText("Tu secreto (se muestra una sola vez)")).toBeTruthy();

    await user.click(await screen.findByRole("button", { name: "Enviar prueba" }));
    expect(await screen.findByText("La prueba llegó (HTTP 200).")).toBeTruthy();
  });

  it("gives the snippet to paste, with instructions and a preview", async () => {
    vi.mocked(saveWidget).mockResolvedValue(integrations());
    const user = renderPage();

    const snippet = await screen.findByText(/widget\.js/);
    expect(snippet.textContent).toBe(
      `<script src="${window.location.origin}/widget.js" data-agencia="AbC123xyz" async></script>`,
    );
    expect(screen.getByText(/Web hecha con Tokko:/)).toBeTruthy();
    expect(screen.getByText(/me interesa la propiedad «2 ambientes luminoso» \(ref\. TKO1234\)/))
      .toBeTruthy();

    const label = screen.getByLabelText("Texto del botón");
    await user.clear(label);
    await user.type(label, "Escribinos");
    await user.click(screen.getByLabelText("Abajo a la izquierda"));
    await user.click(screen.getByRole("button", { name: "Guardar botón" }));

    expect(saveWidget).toHaveBeenCalledWith({
      enabled: true,
      color: "#047857",
      text_color: "#ffffff",
      position: "left",
      label: "Escribinos",
    });
  });

  it("is read-only for agents", async () => {
    vi.mocked(fetchMe).mockResolvedValue(me("agent"));
    renderPage();

    expect(
      await screen.findByText("Solo el dueño o un encargado pueden cambiar las integraciones."),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Probar conexión" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Guardar botón" })).toBeNull();
  });
});
