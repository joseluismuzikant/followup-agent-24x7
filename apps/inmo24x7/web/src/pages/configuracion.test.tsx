import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchMe } from "../api/me";
import { fetchTenantSettings } from "../api/tenant-settings";
import { fetchWhatsAppStatus } from "../api/whatsapp";
import { me, whatsappStatus } from "../test-fixtures";
import { ConfiguracionPage } from "./configuracion";

vi.mock("../api/me", () => ({ fetchMe: vi.fn() }));
vi.mock("../api/tenant-settings", () => ({
  fetchTenantSettings: vi.fn(),
  saveTenantSettings: vi.fn(),
}));
vi.mock("../api/whatsapp", () => ({ fetchWhatsAppStatus: vi.fn() }));
vi.mock("../lib/auth", () => ({ useAuth: () => ({ signOut: vi.fn() }) }));

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
