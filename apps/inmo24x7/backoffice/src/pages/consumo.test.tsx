import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { downloadUsageCsv, fetchTenantUsage, fetchUsage } from "../api/backoffice";
import { businessUsage, tenantUsage, usageFigures, usageReport } from "../test-fixtures";
import { ConsumoPage } from "./consumo";

vi.mock("../api/backoffice", () => ({
  fetchUsage: vi.fn(),
  fetchTenantUsage: vi.fn(),
  downloadUsageCsv: vi.fn(),
}));
vi.mock("../components/RequireAdmin", () => ({
  RequireAdmin: ({ children }: { children: ReactNode }) => children,
}));

function renderPage(path = "/consumo?mes=2026-11") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/consumo" element={<ConsumoPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

describe("Consumo", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchUsage).mockResolvedValue(usageReport());
    vi.mocked(fetchTenantUsage).mockResolvedValue(tenantUsage());
  });

  it("shows the month's totals and one row per business, flagging models without a price", async () => {
    renderPage();

    expect((await screen.findByLabelText(/Costo del LLM/)).textContent).toContain("0,593");
    expect(fetchUsage).toHaveBeenCalledWith("2026-11");
    expect(screen.getByLabelText("Conversaciones").textContent).toContain("12");
    expect(screen.getByLabelText("Parte del simulador").textContent).toContain("25");
    expect(screen.getByText(/Meses en UTC/)).toBeTruthy();
    const rows = screen.getAllByRole("row");
    expect(within(rows[1]!).getByText("Inmobiliaria Sur")).toBeTruthy();
    expect(within(rows[2]!).getByText("sin precio")).toBeTruthy();
    expect(within(rows[1]!).queryByText("sin precio")).toBeNull();
  });

  it("shows the cost as unknown, not zero, when no call had a price", async () => {
    const unpriced = usageFigures({
      llm_calls: 15,
      unpriced_calls: 15,
      cost_usd: "0.000000",
      cost_per_conversation_usd: "0.000000",
      conversations: 3,
    });
    vi.mocked(fetchUsage).mockResolvedValue(
      usageReport({
        totals: unpriced,
        businesses: [businessUsage({ name: "Inmobiliaria Almagro", figures: unpriced })],
      }),
    );
    renderPage();

    const cost = await screen.findByLabelText(/Costo del LLM/);
    expect(cost.textContent).toContain("—");
    expect(cost.textContent).toContain("15 llamadas sin precio");
    expect(screen.getByLabelText("Costo por conversación").textContent).toContain("—");
    const row = screen.getAllByRole("row")[1]!;
    expect(within(row).getByText("sin precio")).toBeTruthy();
    expect(row.textContent).not.toContain("0,00");
  });

  it("downloads the table as CSV", async () => {
    vi.mocked(downloadUsageCsv).mockResolvedValue();
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Exportar CSV" }));

    expect(downloadUsageCsv).toHaveBeenCalledWith("2026-11");
  });

  it("opens one business with its daily chart and the splits", async () => {
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Inmobiliaria Sur" }));

    expect(await screen.findByText("Inmobiliaria Sur · noviembre 2026")).toBeTruthy();
    expect(fetchTenantUsage).toHaveBeenCalledWith("tenant-1", "2026-11");
    const chart = screen.getByRole("img", { name: /Costo \(USD\) \(barras\) y Conversaciones/ });
    expect(chart.querySelectorAll("[data-slot=bar]")).toHaveLength(3);
    expect(screen.getByText("Escribir la respuesta")).toBeTruthy();
    expect(screen.getByText("anthropic:claude-sonnet-5-5")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "← Todos los negocios" }));
    expect(await screen.findByRole("button", { name: "Exportar CSV" })).toBeTruthy();
  });

  it("opens straight on a business from S9's link", async () => {
    renderPage("/consumo?negocio=tenant-1&mes=2026-10");

    expect(await screen.findByText(/Inmobiliaria Sur ·/)).toBeTruthy();
    expect(fetchTenantUsage).toHaveBeenCalledWith("tenant-1", "2026-10");
    expect(fetchUsage).not.toHaveBeenCalled();
  });
});
