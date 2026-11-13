import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchSummary } from "../api/invoices";
import { fetchMe } from "../api/me";
import { fetchOnboarding } from "../api/onboarding";
import { me, onboardingState, summary } from "../test-fixtures";
import { InicioPage } from "./inicio";

vi.mock("../api/me", () => ({ fetchMe: vi.fn() }));
vi.mock("../api/onboarding", () => ({ fetchOnboarding: vi.fn() }));
vi.mock("../api/whatsapp", () => ({
  fetchWhatsAppStatus: vi.fn().mockResolvedValue({ status: "not_connected" }),
}));
vi.mock("../api/invoices", () => ({
  fetchSummary: vi.fn(),
  importInvoices: vi.fn(),
  downloadImportErrors: vi.fn(),
  downloadImportTemplate: vi.fn(),
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <InicioPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("InicioPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchMe).mockResolvedValue(me());
    vi.mocked(fetchSummary).mockResolvedValue(summary());
  });

  it("shows what there is to collect and what is overdue", async () => {
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("done", { invoicesLoaded: true }));
    renderPage();

    const toCollect = await screen.findByRole("region", { name: "Total a cobrar" });
    expect(within(toCollect).getByText(/5\.400\.000/)).toBeTruthy();
    expect(within(toCollect).getByText("32 facturas abiertas")).toBeTruthy();
    const overdue = screen.getByRole("region", { name: "Vencido" });
    expect(within(overdue).getByText(/2\.100\.000/)).toBeTruthy();
    expect(within(overdue).getByText("13 facturas vencidas")).toBeTruthy();
    expect(screen.getByText("Hola, Ascensores Delta")).toBeTruthy();
  });

  it("mentions dollars apart", async () => {
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("done", { invoicesLoaded: true }));
    vi.mocked(fetchSummary).mockResolvedValue(
      summary({ to_collect_usd: { amount: "1200.00", count: 1 } }),
    );
    renderPage();

    const toCollect = await screen.findByRole("region", { name: "Total a cobrar" });
    expect(within(toCollect).getByText("y USD 1.200 en dólares")).toBeTruthy();
  });

  it("shows the empty state and the checklist before any invoice", async () => {
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("reminders"));
    renderPage();

    expect(await screen.findByText("Todavía no cargaste facturas")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Total a cobrar" })).toBeNull();
    expect(screen.getByText("1 de 5 listos")).toBeTruthy();
    expect(screen.getByText("Cargar tus facturas")).toBeTruthy();
    expect(screen.getByText("Conectar WhatsApp")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Continuar configuración" })).toBeTruthy();
  });
});
