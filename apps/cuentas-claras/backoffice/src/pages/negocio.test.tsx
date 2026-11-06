import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchBusiness, reactivateBusiness, suspendBusiness } from "../api/backoffice";
import { businessDetail } from "../test-fixtures";
import { NegocioPage } from "./negocio";

vi.mock("../api/backoffice", () => ({
  fetchBusiness: vi.fn(),
  suspendBusiness: vi.fn(),
  reactivateBusiness: vi.fn(),
}));
vi.mock("../components/RequireAdmin", () => ({
  RequireAdmin: ({ children }: { children: ReactNode }) => children,
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/negocios/33333333-3333-3333-3333-333333333333"]}>
        <Routes>
          <Route path="/negocios/:tenantId" element={<NegocioPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

describe("Detalle del negocio", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchBusiness).mockResolvedValue(businessDetail());
  });

  it("shows the plan, owner, checklist, portfolio and activity", async () => {
    renderPage();

    expect(await screen.findByText("Dueño: dueno@ascensoresdelta.test")).toBeTruthy();
    expect(screen.getByText("Prueba · 12 días")).toBeTruthy();
    expect(screen.getByText("Configuración · 2 de 5")).toBeTruthy();
    expect(screen.getByText("Facturas cargadas")).toBeTruthy();
    expect(screen.getByText("Mercado Pago conectado")).toBeTruthy();
    expect(screen.getByText(/5\.400\.000/)).toBeTruthy();
    expect(screen.getByText("Importó facturas · 40 nuevas, 0 actualizadas, 0 con errores")).toBeTruthy();
    expect(screen.getByText("Marcó una factura como pagada · transferencia")).toBeTruthy();
  });

  it("suspends with a reason", async () => {
    vi.mocked(suspendBusiness).mockResolvedValue(
      businessDetail({ status: "suspended", suspended_reason: "Falta de pago" }),
    );
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Suspender" }));
    const dialog = screen.getByRole("dialog", { name: "Suspender Ascensores Delta" });
    const submit = within(dialog).getByRole("button", { name: "Suspender" }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    await user.type(within(dialog).getByLabelText("Motivo"), "Falta de pago");
    await user.click(submit);

    expect(suspendBusiness).toHaveBeenCalledWith(
      "33333333-3333-3333-3333-333333333333",
      "Falta de pago",
    );
    expect(await screen.findByText("Motivo: Falta de pago")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reactivar" })).toBeTruthy();
  });

  it("reactivates a suspended business", async () => {
    vi.mocked(fetchBusiness).mockResolvedValue(
      businessDetail({ status: "suspended", suspended_reason: "Falta de pago" }),
    );
    vi.mocked(reactivateBusiness).mockResolvedValue(businessDetail());
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Reactivar" }));

    expect(reactivateBusiness).toHaveBeenCalledWith("33333333-3333-3333-3333-333333333333");
    expect(await screen.findByRole("button", { name: "Suspender" })).toBeTruthy();
  });
});
