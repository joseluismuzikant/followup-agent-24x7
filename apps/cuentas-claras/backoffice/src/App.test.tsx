import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createBusiness, fetchBusinesses } from "./api/backoffice";
import { App } from "./App";
import { businessList, businessRow } from "./test-fixtures";

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

describe("Negocios", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchBusinesses).mockResolvedValue(
      businessList([
        businessRow(),
        businessRow({
          id: "44444444-4444-4444-4444-444444444444",
          name: "Monitoreo Sur",
          status: "suspended",
          owner_pending: true,
          owner_email: "duena@monitoreosur.test",
          plan: { plan: "pro", trial_days_left: null },
          onboarding_done: 1,
          clients: 0,
          open_amount: "0.00",
        }),
      ]),
    );
  });

  it("lists each business with owner, plan, onboarding, clients and what is open", async () => {
    renderApp();

    const row = (await screen.findByRole("link", { name: "Ascensores Delta" })).closest("tr")!;
    expect(within(row).getByText("dueno@ascensoresdelta.test")).toBeTruthy();
    expect(within(row).getByText("Prueba · 12 días")).toBeTruthy();
    expect(within(row).getByText("2 de 5")).toBeTruthy();
    expect(within(row).getByText("25")).toBeTruthy();
    expect(within(row).getByText(/5\.400\.000/)).toBeTruthy();

    const other = screen.getByRole("link", { name: "Monitoreo Sur" }).closest("tr")!;
    expect(within(other).getByText("Suspendido")).toBeTruthy();
    expect(within(other).getByText("todavía no entró")).toBeTruthy();
    expect(within(other).getByText("Pro")).toBeTruthy();
  });

  it("searches", async () => {
    const user = renderApp();
    await screen.findByRole("link", { name: "Ascensores Delta" });

    await user.type(screen.getByLabelText("Buscar por nombre o email"), "delta");

    await waitFor(() => expect(fetchBusinesses).toHaveBeenLastCalledWith("delta", 1));
  });

  it("has only Negocios in the nav", async () => {
    renderApp();
    await screen.findByRole("link", { name: "Ascensores Delta" });

    const nav = screen.getAllByRole("navigation")[0]!;
    expect(within(nav).getAllByRole("link").map((link) => link.textContent)).toEqual(["Negocios"]);
  });

  it("says when there are no businesses", async () => {
    vi.mocked(fetchBusinesses).mockResolvedValue(businessList([]));
    renderApp();

    expect(await screen.findByText("Todavía no hay negocios.")).toBeTruthy();
  });

  it("gives a business to its owner's email from Dar de alta and shows the password once", async () => {
    vi.mocked(createBusiness).mockResolvedValue({
      ...businessRow(),
      id: "55555555-5555-5555-5555-555555555555",
      owner_email: "duenio@matafuegos.test",
      suspended_reason: null,
      checklist: [],
      activity: [],
      temporary_password: "Kx7pQ2mN9rTw",
    });
    const user = renderApp();

    await user.click(await screen.findByRole("button", { name: "Dar de alta un negocio" }));
    await user.type(screen.getByLabelText("Nombre del negocio"), "Matafuegos Norte");
    await user.type(screen.getByLabelText("Email del dueño"), "duenio@matafuegos.test");
    await user.click(screen.getByRole("button", { name: "Dar de alta" }));

    expect(await screen.findByText("Kx7pQ2mN9rTw")).toBeTruthy();
    expect(createBusiness).toHaveBeenCalledWith({
      business_name: "Matafuegos Norte",
      business_type: "mantenimiento",
      owner_email: "duenio@matafuegos.test",
    });
    await user.click(screen.getByRole("button", { name: "Listo" }));
    expect(await screen.findByText("Detalle")).toBeTruthy();
  });
});
