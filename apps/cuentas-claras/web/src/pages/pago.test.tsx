import { ApiRequestError } from "@followup/api-client-cuentas-claras";
import type { PaymentPage } from "@followup/api-client-cuentas-claras";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchPaymentPage } from "../api/payments";
import { PagoPage } from "./pago";

vi.mock("../api/payments", () => ({ fetchPaymentPage: vi.fn() }));

const page: PaymentPage = {
  business_name: "Ascensores Delta",
  client_name: "Edificio Güemes",
  invoices: [
    {
      number: "B 0003-00001245",
      due_date: "2026-11-15",
      amount: "180000.00",
      currency: "ARS",
      paid: false,
      status_label: "Por vencer",
    },
  ],
  totals: [{ currency: "ARS", amount: "180000.00" }],
  transfer: { cbu_or_alias: "ascensores.delta", holder: "Ascensores Delta SRL", bank: null },
  mercado_pago_available: false,
  expires_at: "2027-01-10T12:00:00Z",
};

function renderPage(token = "tok") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/p/${token}`]}>
        <Routes>
          <Route path="/p/:token" element={<PagoPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PagoPage (/p/<token>)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the business, the invoices, the total and the transfer details, never indexed", async () => {
    vi.mocked(fetchPaymentPage).mockResolvedValue(page);
    renderPage("abc123");

    expect(await screen.findByRole("heading", { name: "Ascensores Delta" })).toBeTruthy();
    expect(fetchPaymentPage).toHaveBeenCalledWith("abc123");
    expect(screen.getByText("Para Edificio Güemes")).toBeTruthy();
    expect(screen.getByText("B 0003-00001245")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Pronto vas a poder pagar con Mercado Pago" })).toBeTruthy();
    expect(screen.getByText("ascensores.delta")).toBeTruthy();
    expect(document.head.querySelector('meta[name="robots"]')?.getAttribute("content")).toBe(
      "noindex, nofollow",
    );
  });

  it("says when everything is paid", async () => {
    vi.mocked(fetchPaymentPage).mockResolvedValue({
      ...page,
      invoices: [{ ...page.invoices[0]!, paid: true, status_label: "Pagada" }],
      totals: [],
    });
    renderPage();

    expect(await screen.findByText("¡Listo! No hay nada pendiente en este link.")).toBeTruthy();
    expect(screen.queryByText("Cómo pagar")).toBeNull();
  });

  it("an unknown or expired link says so", async () => {
    vi.mocked(fetchPaymentPage).mockRejectedValue(new ApiRequestError(404, "payment_link_not_found"));
    renderPage();

    expect(await screen.findByText("Este link ya no está disponible")).toBeTruthy();
  });
});
