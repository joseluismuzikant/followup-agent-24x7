import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchOnboarding } from "../api/onboarding";
import { fetchWhatsAppStatus } from "../api/whatsapp";
import { isOnboardingDeferred, deferOnboarding } from "../lib/onboarding-deferred";
import { onboardingState } from "../test-fixtures";
import { InicioPage } from "./inicio";

vi.mock("../api/onboarding", () => ({ fetchOnboarding: vi.fn() }));
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
    expect(screen.getByText(/Todavía no hay consultas/)).toBeTruthy();
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

  it("hides the badge when WhatsApp is not connected", async () => {
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("done"));
    vi.mocked(fetchWhatsAppStatus).mockResolvedValue({ status: "disconnected" });
    renderInicio();

    await screen.findByText("Te falta poco para dejarlo completo");
    expect(screen.queryByText(/Agente activo/)).toBeNull();
  });
});
