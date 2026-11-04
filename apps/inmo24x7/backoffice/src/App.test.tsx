import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createBusiness, fetchBusinesses } from "./api/backoffice";
import { App } from "./App";
import { businessDetail, businessList } from "./test-fixtures";

vi.mock("./api/backoffice", () => ({ fetchBusinesses: vi.fn(), createBusiness: vi.fn() }));
vi.mock("./components/RequireAdmin", () => ({
  RequireAdmin: ({ children }: { children: ReactNode }) => children,
}));

function renderApp() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<App />} />
          <Route path="/negocios/:id" element={<p>Detalle</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

describe("Negocios (S8)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchBusinesses).mockResolvedValue(businessList());
  });

  it("shows the four KPIs and the businesses", async () => {
    renderApp();

    expect(await screen.findByRole("link", { name: "Inmobiliaria Sur" })).toBeTruthy();
    for (const [label, value] of [
      ["Activos", "4"],
      ["En prueba", "3"],
      ["Onboarding sin terminar", "2"],
      ["WhatsApp con problemas", "1"],
    ]) {
      expect(screen.getByLabelText(label).textContent).toContain(value);
    }
  });

  it("filters and searches", async () => {
    const user = renderApp();
    await screen.findByRole("link", { name: "Inmobiliaria Sur" });

    await user.click(screen.getByRole("radio", { name: "Necesitan ayuda" }));
    await user.type(screen.getByLabelText("Buscar por nombre o email"), "sur");

    await waitFor(() =>
      expect(fetchBusinesses).toHaveBeenLastCalledWith("needs_help", "sur", 1),
    );
  });

  it("gives a business to its owner's email from Dar de alta", async () => {
    vi.mocked(createBusiness).mockResolvedValue(businessDetail());
    const user = renderApp();

    await user.click(screen.getByRole("button", { name: "Dar de alta un negocio" }));
    await user.type(screen.getByLabelText("Nombre del negocio"), "Palermo Propiedades");
    await user.type(screen.getByLabelText("Email del dueño"), "duenia@palermo.test");
    await user.click(screen.getByRole("button", { name: "Dar de alta" }));

    expect(await screen.findByText("Detalle")).toBeTruthy();
    expect(createBusiness).toHaveBeenCalledWith({
      business_name: "Palermo Propiedades",
      business_type: "inmobiliaria",
      owner_email: "duenia@palermo.test",
    });
  });
});
