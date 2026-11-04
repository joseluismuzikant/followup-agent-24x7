import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { Dashboard } from "@followup/api-client-inmo24x7";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchDashboard } from "../api/dashboard";
import { fetchOnboarding } from "../api/onboarding";
import { fetchWhatsAppStatus } from "../api/whatsapp";
import { isOnboardingDeferred, deferOnboarding } from "../lib/onboarding-deferred";
import { onboardingState, whatsappStatus } from "../test-fixtures";
import { InicioPage } from "./inicio";

vi.mock("../api/onboarding", () => ({ fetchOnboarding: vi.fn() }));
vi.mock("../api/dashboard", () => ({ fetchDashboard: vi.fn() }));

function dashboard(overrides: Partial<Dashboard> = {}): Dashboard {
  return {
    business_name: "Inmobiliaria Sur",
    week_start: "2026-11-02T03:00:00Z",
    received: { total: 0, out_of_hours: 0 },
    qualified: 0,
    visits: { total: 0, confirmed: 0 },
    response_time_seconds: null,
    attention_today: [],
    ...overrides,
  };
}
vi.mock("../api/whatsapp", () => ({ fetchWhatsAppStatus: vi.fn() }));

function renderInicio() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<InicioPage />} />
          <Route path="/onboarding" element={<div>Wizard</div>} />
          <Route path="/agente" element={<div>Agente</div>} />
          <Route path="/consultas" element={<div>Consultas</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Inicio setup checklist", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    deferOnboarding();
    vi.mocked(fetchWhatsAppStatus).mockResolvedValue({ status: "not_connected" });
    vi.mocked(fetchDashboard).mockResolvedValue(dashboard());
  });

  it("shows N de 5 listos with done items as text and pending ones as links", async () => {
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("try"));
    renderInicio();

    expect(await screen.findByText("Te falta poco para dejarlo completo")).toBeTruthy();
    expect(screen.getByText("1 de 5 listos")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Cuenta creada" })).toBeNull();
    expect(screen.getByText("Cuenta creada")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Configurar tu agente" }).getAttribute("href")).toBe(
      "/agente",
    );
    expect(screen.getByRole("link", { name: "Cargar tus propiedades" })).toBeTruthy();
    // Meta verification has no destination yet, so it is not a link.
    expect(screen.queryByRole("link", { name: "Verificar tu empresa en Meta" })).toBeNull();
    expect(await screen.findByText(/Todavía no hay consultas esta semana/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Probar el agente" }).getAttribute("href")).toBe(
      "/probar",
    );
  });

  it("resumes the wizard from Continuar configuración", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("try"));
    renderInicio();

    await user.click(await screen.findByRole("button", { name: "Continuar configuración" }));

    expect(await screen.findByText("Wizard")).toBeTruthy();
    expect(isOnboardingDeferred()).toBe(false);
  });

  it("hides Continuar configuración once onboarding is finished", async () => {
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("done"));
    renderInicio();

    await screen.findByText("Te falta poco para dejarlo completo");
    expect(screen.queryByRole("button", { name: "Continuar configuración" })).toBeNull();
  });

  it("shows Agente activo with the number only when WhatsApp is connected", async () => {
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("done"));
    vi.mocked(fetchWhatsAppStatus).mockResolvedValue({
      status: "connected",
      display_phone_number: "+54 9 11 5555-0100",
    });
    renderInicio();

    expect(await screen.findByText("Agente activo · +54 9 11 5555-0100")).toBeTruthy();
  });

  it("shows a red banner with the translated error while WhatsApp fails", async () => {
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("done"));
    vi.mocked(fetchWhatsAppStatus).mockResolvedValue(
      whatsappStatus({
        status: "error",
        error: {
          code: "token_revoked",
          title: "El permiso de Meta venció",
          message: "Tu agente no puede responder en WhatsApp.",
          action: "Tocá Volver a conectar.",
        },
      }),
    );
    renderInicio();

    const banner = await screen.findByRole("alert");
    expect(banner.textContent).toContain("El permiso de Meta venció");
    expect(screen.getByRole("link", { name: "Volver a conectar" }).getAttribute("href")).toBe(
      "/configuracion#whatsapp",
    );
    expect(screen.queryByText(/Agente activo/)).toBeNull();
  });

  it("hides the badge when WhatsApp is not connected", async () => {
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("done"));
    vi.mocked(fetchWhatsAppStatus).mockResolvedValue({ status: "disconnected" });
    renderInicio();

    await screen.findByText("Te falta poco para dejarlo completo");
    expect(screen.queryByText(/Agente activo/)).toBeNull();
  });
});

describe("Inicio KPIs", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    deferOnboarding();
    vi.mocked(fetchWhatsAppStatus).mockResolvedValue({ status: "not_connected" });
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("done"));
  });

  it("greets the business and explains an empty week", async () => {
    vi.mocked(fetchDashboard).mockResolvedValue(dashboard());
    renderInicio();

    expect(await screen.findByRole("heading", { name: "Hola, Inmobiliaria Sur" })).toBeTruthy();
    expect(screen.getByText("Esto pasó esta semana con tu agente.")).toBeTruthy();
    expect(
      screen.getByText("Todavía no hay consultas esta semana. Probá tu agente o conectá WhatsApp."),
    ).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Consultas recibidas" })).toBeNull();
  });

  it("shows the four KPI cards and Para atender hoy, whose rows open the lead", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchDashboard).mockResolvedValue(
      dashboard({
        received: { total: 12, out_of_hours: 5 },
        qualified: 8,
        visits: { total: 3, confirmed: 1 },
        response_time_seconds: 80,
        attention_today: [
          {
            id: "l1",
            name: "Ana Pérez",
            looking_for: "Alquiler · Palermo",
            status: "visit_proposed",
            created_at: new Date(Date.now() - 3 * 3600_000).toISOString(),
            last_activity_at: new Date().toISOString(),
          },
        ],
      }),
    );
    renderInicio();

    const received = await screen.findByRole("region", { name: "Consultas recibidas" });
    expect(within(received).getByText("12")).toBeTruthy();
    expect(within(received).getByText("5 fuera de horario")).toBeTruthy();
    const qualified = screen.getByRole("region", { name: "Calificadas" });
    expect(within(qualified).getByText("Con zona y presupuesto")).toBeTruthy();
    const visits = screen.getByRole("region", { name: "Visitas agendadas" });
    expect(within(visits).getByText(/El número que importa · 1 confirmadas/)).toBeTruthy();
    const response = screen.getByRole("region", { name: "Respuesta promedio" });
    expect(within(response).getByText("1 min 20 s")).toBeTruthy();
    expect(within(response).getByText("A cualquier hora")).toBeTruthy();

    const row = screen.getByText("Ana Pérez").closest("tr") as HTMLElement;
    expect(within(row).getByText("Visita propuesta")).toBeTruthy();
    expect(within(row).getByText("3 h")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Ver todas" }).getAttribute("href")).toBe(
      "/consultas?tab=attention",
    );
    await user.click(screen.getByRole("link", { name: "Ana Pérez" }));
    expect(await screen.findByText("Consultas")).toBeTruthy();
  });

  it("shows a dash when there is no response time yet", async () => {
    vi.mocked(fetchDashboard).mockResolvedValue(
      dashboard({ received: { total: 1, out_of_hours: 0 } }),
    );
    renderInicio();

    const response = await screen.findByRole("region", { name: "Respuesta promedio" });
    expect(within(response).getByText("—")).toBeTruthy();
  });
});
