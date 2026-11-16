import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchMe } from "../api/me";
import { fetchConditionSettings, saveConditionSettings } from "../api/properties";
import { fetchTenantSettings } from "../api/tenant-settings";
import { fetchWhatsAppStatus } from "../api/whatsapp";
import { EMPTY_CONDITIONS } from "../lib/conditions";
import { me, whatsappStatus } from "../test-fixtures";
import { ConfiguracionPage } from "./configuracion";

vi.mock("../api/me", () => ({ fetchMe: vi.fn() }));
vi.mock("../api/tenant-settings", () => ({
  fetchTenantSettings: vi.fn(),
  saveTenantSettings: vi.fn(),
}));
vi.mock("../api/properties", () => ({
  fetchConditionSettings: vi.fn(),
  saveConditionSettings: vi.fn(),
}));
vi.mock("../api/whatsapp", () => ({ fetchWhatsAppStatus: vi.fn() }));
vi.mock("../lib/auth", () => ({ useAuth: () => ({ signOut: vi.fn() }) }));

const SETTINGS = {
  rent: { ...EMPTY_CONDITIONS },
  sale: { ...EMPTY_CONDITIONS },
  warn_before_visit: true,
  offer_alternatives: true,
  notify_mismatches: true,
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/configuracion#whatsapp"]}>
        <ConfiguracionPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Configuración → WhatsApp", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchTenantSettings).mockResolvedValue({
      business_name: "Inmobiliaria Sur",
      business_type: "inmobiliaria",
      timezone: "America/Argentina/Buenos_Aires",
      business_hours: [],
      notification_emails: ["duena@example.com"],
    });
    vi.mocked(fetchConditionSettings).mockResolvedValue(SETTINGS);
  });

  it("lets owners connect WhatsApp from the section the reconnect email links to", async () => {
    vi.mocked(fetchMe).mockResolvedValue(me("owner"));
    vi.mocked(fetchWhatsAppStatus).mockResolvedValue(whatsappStatus());
    const { container } = renderPage();

    expect(await screen.findByRole("button", { name: "Conectar WhatsApp" })).toBeTruthy();
    expect(container.querySelector("#whatsapp")).not.toBeNull();
  });

  it("shows the error banner and the status, read-only, to agents", async () => {
    vi.mocked(fetchMe).mockResolvedValue(me("agent"));
    vi.mocked(fetchWhatsAppStatus).mockResolvedValue(
      whatsappStatus({
        status: "error",
        display_phone_number: "+54 9 11 5555-0100",
        error: {
          code: "token_revoked",
          title: "El permiso de Meta venció",
          message: "Tu agente no puede responder en WhatsApp.",
          action: "Tocá Volver a conectar.",
        },
      }),
    );
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("El permiso de Meta venció");
    expect(screen.getByLabelText("Estado de WhatsApp")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Conectar WhatsApp" })).toBeNull();
  });
});

describe("Configuración → Condiciones generales", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchTenantSettings).mockResolvedValue({
      business_name: "Inmobiliaria Sur",
      business_type: "inmobiliaria",
      timezone: "America/Argentina/Buenos_Aires",
      business_hours: [],
      notification_emails: [],
    });
    vi.mocked(fetchWhatsAppStatus).mockResolvedValue(whatsappStatus());
    vi.mocked(fetchConditionSettings).mockResolvedValue(SETTINGS);
  });

  it("saves the defaults per operation and the three switches", async () => {
    vi.mocked(fetchMe).mockResolvedValue(me("owner"));
    vi.mocked(saveConditionSettings).mockImplementation(async (value) => value);
    const user = userEvent.setup();
    renderPage();

    const card = within(
      (await screen.findByText("Condiciones generales")).closest("#condiciones") as HTMLElement,
    );
    const warn = await card.findByLabelText(/Avisar los requisitos antes de coordinar/);
    expect((warn as HTMLInputElement).checked).toBe(true);
    await user.click(card.getByRole("button", { name: "Seguro de caución" }));
    await user.click(card.getByRole("radio", { name: "Venta" }));
    const credit = within(card.getByRole("radiogroup", { name: "Apta crédito hipotecario" }));
    await user.click(credit.getByRole("radio", { name: "Sí" }));
    await user.click(card.getByLabelText(/Notificar al equipo/));
    await user.click(card.getByRole("button", { name: "Guardar condiciones" }));

    expect(vi.mocked(saveConditionSettings)).toHaveBeenCalledWith({
      rent: { ...EMPTY_CONDITIONS, garantias: ["caucion"] },
      sale: { ...EMPTY_CONDITIONS, apto_credito: true },
      warn_before_visit: true,
      offer_alternatives: true,
      notify_mismatches: false,
    });
    expect(await card.findByText("Condiciones guardadas.")).toBeTruthy();
  });

  it("is read-only for agents", async () => {
    vi.mocked(fetchMe).mockResolvedValue(me("agent"));
    renderPage();

    expect(await screen.findByText("Solo el dueño o un encargado pueden cambiarlas.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Guardar condiciones" })).toBeNull();
  });
});
