import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { fetchErrors, fetchPlans, fetchSystemHealth } from "../api/backoffice";
import { errorList, systemHealth } from "../test-fixtures";
import { PlanesPage } from "./planes";
import { SistemaPage } from "./sistema";

vi.mock("../api/backoffice", () => ({
  fetchSystemHealth: vi.fn(),
  fetchPlans: vi.fn(),
  fetchErrors: vi.fn(),
}));
vi.mock("../components/RequireAdmin", () => ({
  RequireAdmin: ({ children }: { children: ReactNode }) => children,
}));

function renderWith(page: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{page}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Salud del sistema and Planes", () => {
  it("shows the recent errors from Sentry with a link to all of them", async () => {
    vi.mocked(fetchSystemHealth).mockResolvedValue(systemHealth());
    vi.mocked(fetchErrors).mockResolvedValue(errorList());
    renderWith(<SistemaPage />);

    expect(await screen.findByText("RuntimeError: boom")).toBeTruthy();
    expect(fetchErrors).toHaveBeenCalledWith({ period: "24h", limit: 10 });
    expect(screen.getByRole("link", { name: "RuntimeError: boom" }).getAttribute("href")).toBe(
      "https://acme.sentry.io/issues/101/",
    );
    expect(screen.getAllByText("12 veces")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Ver todos en Sentry" }).getAttribute("href")).toBe(
      "https://acme.sentry.io/issues/",
    );
  });

  it("says when Sentry does not answer", async () => {
    vi.mocked(fetchSystemHealth).mockResolvedValue(systemHealth());
    vi.mocked(fetchErrors).mockResolvedValue(errorList({ available: false, issues: [] }));
    renderWith(<SistemaPage />);

    expect(await screen.findByText(/Sentry no respondió/)).toBeTruthy();
  });

  it("shows jobs, webhooks, failed sends by Meta code, version and database", async () => {
    vi.mocked(fetchSystemHealth).mockResolvedValue(systemHealth());
    vi.mocked(fetchErrors).mockResolvedValue(errorList({ issues: [] }));
    renderWith(<SistemaPage />);

    expect((await screen.findByLabelText("Webhooks (última hora)")).textContent).toContain("42");
    expect(screen.getByLabelText("Firmas rechazadas (24 h)").textContent).toContain("2");
    expect(screen.getByLabelText("Job en cola más viejo").textContent).toContain("2 min");
    expect(screen.getByText("whatsapp.send")).toBeTruthy();
    expect(screen.getByText("Muertos (24 h)")).toBeTruthy();
    expect(screen.getByText("Código de Meta 131026")).toBeTruthy();
    expect(screen.getByText("Base de datos OK")).toBeTruthy();
    expect(screen.getByText(/commit abc1234/)).toBeTruthy();
  });

  it("lists the plans with how many businesses use each", async () => {
    vi.mocked(fetchPlans).mockResolvedValue([
      { plan: "trial", name: "Prueba", monthly_conversations: 1000, tenants: 3 },
      { plan: "pro", name: "Pro", monthly_conversations: 1000, tenants: 1 },
    ]);
    renderWith(<PlanesPage />);

    expect(await screen.findByText("3 negocios")).toBeTruthy();
    expect(screen.getByText("1 negocio")).toBeTruthy();
    expect(screen.getAllByText("1.000 conversaciones por mes")).toHaveLength(2);
  });
});
